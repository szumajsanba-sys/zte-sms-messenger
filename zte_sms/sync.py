from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from .cleanup import SmsCleanupService
from .client import ZteClient
from .decoder import SmsDecoder, read_text_file
from .models import AppSettings, SyncResult
from .settings import DECODED_DIR, RAW_DIR
from .storage import SmsStorage

import hashlib

LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[str], None]


class SyncService:
    def __init__(self, settings: AppSettings, storage: SmsStorage | None = None) -> None:
        self.settings = settings
        self.storage = storage or SmsStorage()
        self.decoder = SmsDecoder()
        self._last_raw_hash: str | None = None
        self._last_found_count: int = 0
        self._has_saved_initial_backup: bool = False

    def sync_from_router(self, progress: ProgressCallback | None = None, cleanup: bool = False, dry_run: bool | None = None) -> SyncResult:
        progress = progress or (lambda _message: None)
        total_found = 0
        total_new = 0
        total_deleted = 0
        raw_path: Path | None = None
        decoded_path: Path | None = None
        all_warnings: list[str] = []
        cleanup_logs: list[str] = []
        effective_dry_run = dry_run if dry_run is not None else self.settings.dry_run_delete
        try:
            progress("Подключение к роутеру")
            client = ZteClient(self.settings)
            if not client.check_router():
                raise RuntimeError("Роутер недоступен")

            progress("Авторизация")
            auth = client.ensure_authenticated()
            if not auth.ok:
                raise RuntimeError(auth.message)

            max_cleanup_rounds = 10 if cleanup else 1
            for round_index in range(max_cleanup_rounds):
                progress("Получаю SMS" if round_index == 0 else f"Получаю SMS, проход {round_index + 1}")
                raw_text = client.fetch_sms_raw()
                raw_hash = hashlib.md5(raw_text.encode("utf-8")).hexdigest()

                # FAST PATH: If modem payload hasn't changed at all and it's not a cleanup run,
                # return immediately in ~0.0001s without any decoding, disk writes, or SQL queries!
                if not cleanup and raw_hash == self._last_raw_hash and self._has_saved_initial_backup:
                    LOGGER.debug("Sync: router payload unchanged (hash %s), 0 new messages", raw_hash[:8])
                    return SyncResult(
                        status="ok",
                        messages_found=self._last_found_count,
                        messages_new=0,
                        messages_deleted_from_router=0,
                    )

                # SLOW PATH: Decode only when data has changed or on initial run
                progress("Декодирую")
                decode_result = self.decoder.decode_response_text(raw_text, mem_store=self.settings.mem_store)
                all_warnings.extend(decode_result.warnings)
                total_found += len(decode_result.messages)

                if not decode_result.messages:
                    self._last_raw_hash = raw_hash
                    self._last_found_count = 0
                    break

                progress("Сохраняю в SQLite")
                new_count = self.storage.insert_messages(decode_result.messages)
                total_new += new_count

                # Only write backups to disk if new messages were found OR if we haven't saved an initial backup yet
                if new_count > 0 or not self._has_saved_initial_backup:
                    raw_path = self.save_raw_backup(raw_text)
                    decoded_path = self.save_decoded_backup(decode_result.messages)
                    self._has_saved_initial_backup = True

                self._last_raw_hash = raw_hash
                self._last_found_count = len(decode_result.messages)

                should_cleanup = cleanup or (
                    self.settings.auto_cleanup
                    and len(decode_result.messages) >= self.settings.cleanup_threshold
                    and not (self.settings.safe_mode and decode_result.suspicious)
                )
                if not should_cleanup:
                    break
                if self.settings.safe_mode and decode_result.suspicious:
                    all_warnings.append("Безопасный режим: очистка остановлена из-за предупреждений декодирования.")
                    break

                progress("Очищаю память роутера")
                cleaner = SmsCleanupService(client, self.storage)
                ids = [msg.zte_id for msg in decode_result.messages if msg.zte_id]
                deleted_count, logs = cleaner.delete_saved_messages(
                    self.settings.mem_store,
                    ids,
                    dry_run=effective_dry_run,
                )
                total_deleted += deleted_count
                cleanup_logs.extend(logs)
                LOGGER.info("Cleanup logs: %s", logs)
                if effective_dry_run:
                    all_warnings.append("Dry-run удаления включен: SMS на роутере не удалялись.")
                    break
                else:
                    self._last_raw_hash = None
                    self._last_found_count = 0

                progress("Проверяю очистку")
                remaining_raw = client.fetch_sms_raw()
                remaining = self.decoder.decode_response_text(remaining_raw, mem_store=self.settings.mem_store)
                remaining_ids = {msg.zte_id for msg in remaining.messages if msg.zte_id}
                still_present = [msg_id for msg_id in ids if msg_id in remaining_ids]
                if still_present:
                    all_warnings.append(f"Роутер все еще показывает {len(still_present)} SMS из списка удаления.")
                    break
                if not remaining.messages:
                    break
            else:
                all_warnings.append("Очистка остановлена: достигнут лимит 10 проходов.")

            status = "ok"
            duplicates_removed = self.storage.purge_semantic_duplicates()
            if duplicates_removed:
                all_warnings.append(f"Удалены локальные дубли в SQLite: {duplicates_removed}.")
            self.storage.finish_sync_run(run_id, status, total_found, total_new, total_deleted)
            return SyncResult(
                status=status,
                messages_found=total_found,
                messages_new=total_new,
                messages_deleted_from_router=total_deleted,
                raw_backup_path=str(raw_path) if raw_path else None,
                decoded_backup_path=str(decoded_path) if decoded_path else None,
                warnings=all_warnings,
                details=cleanup_logs,
            )
        except Exception as exc:
            LOGGER.exception("Sync failed")
            self.storage.finish_sync_run(run_id, "error", error=str(exc))
            return SyncResult(status="error", error=str(exc))

    def import_from_file(self, path: str, progress: ProgressCallback | None = None) -> SyncResult:
        progress = progress or (lambda _message: None)
        run_id = self.storage.start_sync_run()
        try:
            progress("Читаю локальный JSON")
            raw_text = read_text_file(path)
            raw_path = self.save_raw_backup(raw_text)
            progress("Декодирую")
            decode_result = self.decoder.decode_response_text(raw_text, mem_store=self.settings.mem_store)
            decoded_path = self.save_decoded_backup(decode_result.messages)
            progress("Сохраняю в SQLite")
            new_count = self.storage.insert_messages(decode_result.messages)
            self.storage.finish_sync_run(run_id, "ok", len(decode_result.messages), new_count, 0)
            return SyncResult(
                status="ok",
                messages_found=len(decode_result.messages),
                messages_new=new_count,
                raw_backup_path=str(raw_path),
                decoded_backup_path=str(decoded_path),
                warnings=decode_result.warnings,
            )
        except Exception as exc:
            LOGGER.exception("Import failed")
            self.storage.finish_sync_run(run_id, "error", error=str(exc))
            return SyncResult(status="error", error=str(exc))

    def save_raw_backup(self, raw_text: str) -> Path:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = RAW_DIR / f"sms_response_{stamp}.json"
        path.write_text(raw_text, encoding="utf-8")
        return path

    def save_decoded_backup(self, messages) -> Path:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = DECODED_DIR / f"sms_decoded_{stamp}.json"
        data = self.storage.as_serializable_messages(messages)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
