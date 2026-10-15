from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from zte_sms.models import SyncResult
from zte_sms.sync import SyncService


class SyncWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)

    def __init__(self, service: SyncService, mode: str, path: str | None = None, cleanup: bool = False) -> None:
        super().__init__()
        self.service = service
        self.mode = mode
        self.path = path
        self.cleanup = cleanup

    @Slot()
    def run(self) -> None:
        if self.mode == "file" and self.path:
            result = self.service.import_from_file(self.path, self.progress.emit)
        elif self.mode == "cleanup":
            result = self.service.sync_from_router(self.progress.emit, cleanup=True)
        else:
            result = self.service.sync_from_router(self.progress.emit, cleanup=self.cleanup)
        self.finished.emit(result)
