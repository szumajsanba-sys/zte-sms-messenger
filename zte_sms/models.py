from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class AppSettings:
    router_url: str = "http://192.168.0.1"
    password: str = "admin"
    mem_store: int = 1
    data_per_page: int = 500
    request_timeout: int = 75
    retry_count: int = 2
    cleanup_threshold: int = 50
    auto_cleanup: bool = False
    confirm_auto_cleanup: bool = True
    safe_mode: bool = True
    dry_run_delete: bool = True
    theme: str = "light"
    language: str = "en"


@dataclass(slots=True)
class DecodedSms:
    zte_id: str
    sender_raw: str
    sender_decoded: str
    content_raw: str
    content_decoded: str
    zte_date_raw: str
    received_at: str | None
    mem_store: int
    raw_json: dict[str, Any]
    source_hash: str
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DecodeResult:
    messages: list[DecodedSms]
    warnings: list[str]
    suspicious: bool = False


@dataclass(slots=True)
class SyncResult:
    status: str
    messages_found: int = 0
    messages_new: int = 0
    messages_deleted_from_router: int = 0
    raw_backup_path: str | None = None
    decoded_backup_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    error: str | None = None
