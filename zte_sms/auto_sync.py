from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable

from .models import AppSettings, SyncResult
from .storage import SmsStorage
from .sync import SyncService

LOGGER = logging.getLogger(__name__)


class AutoSyncEngine:
    def __init__(
        self,
        settings: AppSettings,
        storage: SmsStorage | None = None,
        interval_seconds: float = 5.0,
        on_update_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage or SmsStorage()
        self.sync_service = SyncService(self.settings, self.storage)
        self.interval = max(2.0, float(interval_seconds))
        self.on_update = on_update_callback

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._trigger_event = threading.Event()
        self._thread: threading.Thread | None = None

        self.is_syncing = False
        self.is_connected = False
        self.last_sync_time: str | None = None
        self.last_status: str = "starting"
        self.last_error: str | None = None
        self.last_new_count: int = 0
        self.total_synced_runs: int = 0
        self.last_run_duration: float = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="ZteAutoSyncThread", daemon=True)
        self._thread.start()
        LOGGER.info("AutoSyncEngine started (interval: %.1fs)", self.interval)

    def stop(self) -> None:
        self._stop_event.set()
        self._trigger_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        LOGGER.info("AutoSyncEngine stopped")

    def trigger_now(self) -> None:
        self._trigger_event.set()

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            total_msgs = 0
            try:
                total_msgs = self.storage.count_messages()
            except Exception:
                pass

            return {
                "is_syncing": self.is_syncing,
                "is_connected": self.is_connected,
                "last_sync_time": self.last_sync_time,
                "last_status": self.last_status,
                "last_error": self.last_error,
                "last_new_count": self.last_new_count,
                "total_synced_runs": self.total_synced_runs,
                "last_run_duration": round(self.last_run_duration, 2),
                "interval_seconds": self.interval,
                "router_url": self.settings.router_url,
                "total_messages": total_msgs,
                "db_version": getattr(self.storage, "version", 0),
            }

    def _run_loop(self) -> None:
        # Initial sync immediately upon startup
        self._perform_sync()

        while not self._stop_event.is_set():
            # Wait for either interval timeout or an explicit trigger
            triggered = self._trigger_event.wait(timeout=self.interval)
            if self._stop_event.is_set():
                break
            if triggered:
                self._trigger_event.clear()

            self._perform_sync()

    def _perform_sync(self) -> None:
        with self._lock:
            if self.is_syncing:
                return
            self.is_syncing = True
            self.last_status = "syncing"

        start_t = time.monotonic()
        result: SyncResult | None = None
        error_msg: str | None = None

        try:
            LOGGER.debug("AutoSync: starting sync with router %s", self.settings.router_url)
            result = self.sync_service.sync_from_router(cleanup=False)
            if result.status == "ok":
                is_connected = True
                status_text = "connected"
                new_count = result.messages_new
            else:
                is_connected = False
                status_text = "error"
                new_count = 0
                error_msg = result.error or "Router error"
        except Exception as exc:
            LOGGER.warning("AutoSync: router sync failed: %s", exc)
            is_connected = False
            status_text = "error"
            new_count = 0
            error_msg = str(exc)

        duration = time.monotonic() - start_t
        now_str = datetime.now().strftime("%H:%M:%S")

        with self._lock:
            self.is_syncing = False
            self.is_connected = is_connected
            self.last_status = status_text
            self.last_error = error_msg
            self.last_sync_time = now_str
            self.last_new_count = new_count
            self.last_run_duration = duration
            self.total_synced_runs += 1

        if self.on_update:
            try:
                self.on_update(self.get_status())
            except Exception as e:
                LOGGER.warning("on_update callback failed: %s", e)
