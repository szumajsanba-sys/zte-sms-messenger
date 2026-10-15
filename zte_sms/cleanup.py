from __future__ import annotations

import logging

from .client import ZteClient
from .storage import SmsStorage

LOGGER = logging.getLogger(__name__)


class SmsCleanupService:
    def __init__(self, client: ZteClient, storage: SmsStorage, batch_size: int = 20) -> None:
        self.client = client
        self.storage = storage
        self.batch_size = batch_size

    def delete_saved_messages(self, mem_store: int, zte_ids: list[str] | None = None, dry_run: bool = True) -> tuple[int, list[str]]:
        ids = zte_ids or self.storage.router_saved_message_ids(mem_store)
        accepted: list[str] = []
        logs: list[str] = []
        for start in range(0, len(ids), self.batch_size):
            batch = ids[start : start + self.batch_size]
            ok, text = self.client.delete_sms(batch, dry_run=dry_run)
            logs.append(f"{'OK' if ok else 'ERROR'} {batch}: {text}")
            LOGGER.info("Cleanup batch %s: %s", batch, text)
            if ok:
                accepted.extend(batch)
                if not dry_run:
                    self.storage.mark_deleted_from_router(batch, mem_store)
            else:
                break
        return 0 if dry_run else len(accepted), logs
