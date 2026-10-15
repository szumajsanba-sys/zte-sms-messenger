from __future__ import annotations

import json
import logging
import mimetypes
import os
import socketserver
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .auto_sync import AutoSyncEngine
from .models import AppSettings
from .settings import ROOT_DIR, load_settings, save_settings
from .storage import SmsStorage

LOGGER = logging.getLogger(__name__)


class ZteApiHandler(BaseHTTPRequestHandler):
    storage: SmsStorage
    auto_sync: AutoSyncEngine
    settings: AppSettings
    web_dir: Path

    def send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/status":
            self.handle_get_status()
        elif path == "/api/chats":
            self.handle_get_chats(query)
        elif path == "/api/messages":
            self.handle_get_messages(query)
        elif path == "/api/settings":
            self.handle_get_settings()
        elif path == "/api/export":
            self.handle_export(query)
        else:
            self.handle_static_file(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}

        if path == "/api/sync":
            self.auto_sync.trigger_now()
            self.send_json({"ok": True, "message": "Sync triggered"})
        elif path == "/api/mark_read":
            sender_id = data.get("sender_id")
            if sender_id is not None:
                self.storage.mark_sender_read(int(sender_id))
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "sender_id is required"}, 400)
        elif path == "/api/settings":
            self.handle_update_settings(data)
        elif path == "/api/cleanup":
            dry_run = data.get("dry_run", True)
            try:
                # Trigger cleanup via sync service
                result = self.auto_sync.sync_service.sync_from_router(cleanup=True)
                self.send_json({"ok": True, "result": result.status, "deleted": result.messages_deleted_from_router, "details": result.details})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
        else:
            self.send_error(404, "Endpoint not found")

    def handle_get_status(self) -> None:
        status = self.auto_sync.get_status()
        self.send_json(status)

    def handle_get_chats(self, query: dict[str, list[str]]) -> None:
        search = query.get("search", [""])[0]
        filter_mode = query.get("filter", ["all"])[0]
        rows = self.storage.get_chats(search=search, filter_mode=filter_mode)
        chats = [dict(r) for r in rows]
        self.send_json({"chats": chats, "count": len(chats)})

    def handle_get_messages(self, query: dict[str, list[str]]) -> None:
        sender_id_str = query.get("sender_id", [None])[0]
        if not sender_id_str:
            self.send_json({"error": "sender_id required"}, 400)
            return
        sender_id = int(sender_id_str)
        rows = self.storage.get_messages_for_sender(sender_id)
        messages = [dict(r) for r in rows]
        self.send_json({"messages": messages, "count": len(messages)})

    def handle_get_settings(self) -> None:
        from dataclasses import asdict
        self.send_json(asdict(self.settings))

    def handle_update_settings(self, data: dict[str, Any]) -> None:
        from dataclasses import asdict
        current = asdict(self.settings)
        for k, v in data.items():
            if k in current:
                setattr(self.settings, k, v)
        save_settings(self.settings)
        # update services
        self.auto_sync.settings = self.settings
        self.auto_sync.sync_service.settings = self.settings
        self.send_json({"ok": True, "settings": asdict(self.settings)})

    def handle_export(self, query: dict[str, list[str]]) -> None:
        fmt = query.get("format", ["csv"])[0].lower()
        if fmt not in {"csv", "json", "txt"}:
            fmt = "csv"
        path = self.storage.export_all(fmt)
        if not path.exists():
            self.send_error(404, "Export file not generated")
            return
        data = path.read_bytes()
        mime = "text/csv; charset=utf-8" if fmt == "csv" else ("application/json" if fmt == "json" else "text/plain")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def handle_static_file(self, req_path: str) -> None:
        clean_path = req_path.lstrip("/")
        if not clean_path or clean_path in {"index.html", ""}:
            target_file = self.web_dir / "index.html"
        else:
            target_file = (self.web_dir / clean_path).resolve()
            # Prevent path traversal
            if not str(target_file).startswith(str(self.web_dir.resolve())):
                self.send_error(403, "Access denied")
                return

        if not target_file.exists() or target_file.is_dir():
            target_file = self.web_dir / "index.html"

        if not target_file.exists():
            self.send_error(404, "File not found")
            return

        mime_type, _ = mimetypes.guess_type(str(target_file))
        mime_type = mime_type or "application/octet-stream"
        content = target_file.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8" if "text" in mime_type or "html" in mime_type or "json" in mime_type or "javascript" in mime_type else mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def address_string(self) -> str:
        # Crucial for Windows: avoid reverse DNS lookup (socket.getfqdn) which causes 1-2s delay per request!
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def log_message(self, format: str, *args: Any) -> None:
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug("%s - - %s", self.client_address[0] if self.client_address else "127.0.0.1", format % args)


def create_server(
    port: int = 8080,
    storage: SmsStorage | None = None,
    settings: AppSettings | None = None,
    auto_sync: AutoSyncEngine | None = None,
    web_dir: Path | None = None,
) -> tuple[ThreadingHTTPServer, int]:
    settings = settings or load_settings()
    storage = storage or SmsStorage()
    auto_sync = auto_sync or AutoSyncEngine(settings, storage, interval_seconds=5.0)

    chosen_web_dir = web_dir or (ROOT_DIR / "web")
    if not chosen_web_dir.exists():
        chosen_web_dir = ROOT_DIR / "standalone_viewer"

    class BoundHandler(ZteApiHandler):
        pass

    BoundHandler.storage = storage
    BoundHandler.settings = settings
    BoundHandler.auto_sync = auto_sync
    BoundHandler.web_dir = chosen_web_dir

    # Try binding to port, if busy try next ports
    actual_port = port
    max_attempts = 10
    httpd = None

    for i in range(max_attempts):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", actual_port), BoundHandler)
            break
        except OSError:
            actual_port += 1

    if not httpd:
        raise RuntimeError(f"Could not bind to any port between {port} and {port + max_attempts}")

    return httpd, actual_port
