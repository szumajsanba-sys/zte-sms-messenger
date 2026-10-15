from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .decoder import normalize_sender
from .models import DecodedSms
from .settings import DB_DIR, EXPORT_DIR


class SmsStorage:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_DIR / "sms.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.version: int = int(datetime.now().timestamp() * 1000)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS senders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_key TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    normalized_number TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    unread_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zte_id TEXT,
                    sender_id INTEGER NOT NULL REFERENCES senders(id),
                    sender_raw TEXT,
                    sender_decoded TEXT,
                    content_raw TEXT,
                    content_decoded TEXT,
                    zte_date_raw TEXT,
                    received_at TEXT,
                    imported_at TEXT NOT NULL,
                    mem_store INTEGER NOT NULL,
                    source_hash TEXT NOT NULL UNIQUE,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    is_deleted_from_router INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
                CREATE INDEX IF NOT EXISTS idx_messages_received ON messages(received_at);
                CREATE INDEX IF NOT EXISTS idx_messages_router_delete ON messages(is_deleted_from_router, zte_id);

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    messages_found INTEGER NOT NULL DEFAULT 0,
                    messages_new INTEGER NOT NULL DEFAULT 0,
                    messages_deleted_from_router INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                """
            )

    def start_sync_run(self) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sync_runs(started_at, status) VALUES(?, ?)",
                (now, "running"),
            )
            return int(cur.lastrowid)

    def finish_sync_run(
        self,
        run_id: int,
        status: str,
        messages_found: int = 0,
        messages_new: int = 0,
        messages_deleted_from_router: int = 0,
        error: str | None = None,
    ) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at=?, status=?, messages_found=?, messages_new=?,
                    messages_deleted_from_router=?, error=?
                WHERE id=?
                """,
                (now, status, messages_found, messages_new, messages_deleted_from_router, error, run_id),
            )

    def upsert_sender(self, conn: sqlite3.Connection, sender_decoded: str) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        display = sender_decoded.strip() or "Без отправителя"
        sender_key = normalize_sender(display) or "unknown"
        normalized_number = sender_key if sender_key[:1].isdigit() or sender_key.startswith("+") else None
        row = conn.execute("SELECT id FROM senders WHERE sender_key=?", (sender_key,)).fetchone()
        if row:
            conn.execute(
                "UPDATE senders SET display_name=?, normalized_number=?, updated_at=? WHERE id=?",
                (display, normalized_number, now, row["id"]),
            )
            return int(row["id"])

        cur = conn.execute(
            """
            INSERT INTO senders(sender_key, display_name, normalized_number, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (sender_key, display, normalized_number, now, now),
        )
        return int(cur.lastrowid)

    def insert_messages(self, messages: list[DecodedSms]) -> int:
        if not messages:
            return 0
        inserted = 0
        imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.connect() as conn:
            # 1 single query to fetch all known source_hashes in memory
            existing_hashes = {
                row[0] for row in conn.execute("SELECT source_hash FROM messages").fetchall()
            }
            # Fast filter: completely skip already saved messages without any database queries!
            new_messages = [m for m in messages if m.source_hash not in existing_hashes]
            if not new_messages:
                return 0

            for msg in new_messages:
                sender_id = self.upsert_sender(conn, msg.sender_decoded)
                try:
                    conn.execute(
                        """
                        INSERT INTO messages(
                            zte_id, sender_id, sender_raw, sender_decoded, content_raw,
                            content_decoded, zte_date_raw, received_at, imported_at,
                            mem_store, source_hash, raw_json
                        )
                        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            msg.zte_id,
                            sender_id,
                            msg.sender_raw,
                            msg.sender_decoded,
                            msg.content_raw,
                            msg.content_decoded,
                            msg.zte_date_raw,
                            msg.received_at,
                            imported_at,
                            msg.mem_store,
                            msg.source_hash,
                            json.dumps(msg.raw_json, ensure_ascii=False),
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass

            if inserted > 0:
                self.recalculate_unread_counts(conn)
                self.version = int(datetime.now().timestamp() * 1000)
        return inserted

    def purge_semantic_duplicates(self) -> int:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    MIN(id) AS keep_id,
                    GROUP_CONCAT(id) AS all_ids,
                    COUNT(*) AS count
                FROM messages
                GROUP BY sender_id, content_decoded, COALESCE(received_at, ''), mem_store
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            delete_ids: list[int] = []
            for row in rows:
                ids = [int(value) for value in row["all_ids"].split(",")]
                keep_id = int(row["keep_id"])
                delete_ids.extend(msg_id for msg_id in ids if msg_id != keep_id)
            if delete_ids:
                placeholders = ",".join("?" for _ in delete_ids)
                conn.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", delete_ids)
                self.recalculate_unread_counts(conn)
                self.version = int(datetime.now().timestamp() * 1000)
            return len(delete_ids)

    def recalculate_unread_counts(self, conn: sqlite3.Connection | None = None) -> None:
        owns_conn = conn is None
        conn = conn or self.connect()
        try:
            conn.execute(
                """
                UPDATE senders
                SET unread_count = (
                    SELECT COUNT(*) FROM messages
                    WHERE messages.sender_id = senders.id AND messages.is_read = 0
                )
                """
            )
        finally:
            if owns_conn:
                conn.commit()
                conn.close()

    def get_chats(self, search: str = "", filter_mode: str = "all") -> list[sqlite3.Row]:
        clauses = []
        params: list[Any] = []
        if search:
            clauses.append("(s.display_name LIKE ? OR m.content_decoded LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if filter_mode == "unread":
            clauses.append("s.unread_count > 0")
        elif filter_mode == "today":
            clauses.append("date(m.received_at) = date('now', 'localtime')")
        elif filter_mode == "week":
            clauses.append("datetime(m.received_at) >= datetime('now', '-7 days', 'localtime')")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT
                    s.id, s.display_name, s.unread_count,
                    MAX(COALESCE(m.received_at, m.imported_at)) AS last_at,
                    (SELECT content_decoded FROM messages mm
                     WHERE mm.sender_id=s.id
                     ORDER BY COALESCE(mm.received_at, mm.imported_at) DESC, mm.id DESC LIMIT 1) AS last_text,
                    COUNT(m.id) AS message_count
                FROM senders s
                JOIN messages m ON m.sender_id = s.id
                {where}
                GROUP BY s.id
                ORDER BY last_at DESC
                """,
                params,
            ).fetchall()

    def get_messages_for_sender(self, sender_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM messages
                WHERE sender_id=?
                ORDER BY COALESCE(received_at, imported_at) ASC, id ASC
                """,
                (sender_id,),
            ).fetchall()

    def mark_sender_read(self, sender_id: int) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE messages SET is_read=1 WHERE sender_id=?", (sender_id,))
            self.recalculate_unread_counts(conn)
        self.version = int(datetime.now().timestamp() * 1000)

    def count_messages(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])

    def router_saved_message_ids(self, mem_store: int) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT zte_id FROM messages
                WHERE mem_store=? AND is_deleted_from_router=0 AND zte_id IS NOT NULL AND zte_id != ''
                ORDER BY CAST(zte_id AS INTEGER) DESC
                """,
                (mem_store,),
            ).fetchall()
        return [str(row["zte_id"]) for row in rows]

    def mark_deleted_from_router(self, zte_ids: list[str], mem_store: int) -> None:
        if not zte_ids:
            return
        placeholders = ",".join("?" for _ in zte_ids)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE messages SET is_deleted_from_router=1 WHERE mem_store=? AND zte_id IN ({placeholders})",
                [mem_store, *zte_ids],
            )

    def export_all(self, fmt: str = "csv") -> Path:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.display_name, m.*
                FROM messages m
                JOIN senders s ON s.id=m.sender_id
                ORDER BY COALESCE(m.received_at, m.imported_at) ASC, m.id ASC
                """
            ).fetchall()

        if fmt == "json":
            path = EXPORT_DIR / f"sms_export_{stamp}.json"
            data = [dict(row) for row in rows]
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return path
        if fmt == "txt":
            path = EXPORT_DIR / f"sms_export_{stamp}.txt"
            with path.open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write("=" * 80 + "\n")
                    fh.write(f"Дата: {row['received_at'] or row['imported_at']}\n")
                    fh.write(f"От: {row['display_name']}\n\n")
                    fh.write((row["content_decoded"] or "") + "\n\n")
            return path

        path = EXPORT_DIR / f"sms_export_{stamp}.csv"
        fields = ["id", "zte_id", "display_name", "content_decoded", "received_at", "mem_store", "is_read"]
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row[field] for field in fields})
        return path

    def as_serializable_messages(self, messages: list[DecodedSms]) -> list[dict[str, Any]]:
        return [asdict(msg) for msg in messages]
