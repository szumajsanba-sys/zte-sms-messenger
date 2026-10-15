from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import AppSettings


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
DB_DIR = DATA_DIR / "db"
RAW_DIR = DATA_DIR / "raw"
DECODED_DIR = DATA_DIR / "decoded"
EXPORT_DIR = DATA_DIR / "exports"
LOG_DIR = ROOT_DIR / "logs"
SETTINGS_PATH = CONFIG_DIR / "settings.json"


def ensure_directories() -> None:
    for path in [CONFIG_DIR, DB_DIR, RAW_DIR, DECODED_DIR, EXPORT_DIR, LOG_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def load_settings() -> AppSettings:
    ensure_directories()
    if not SETTINGS_PATH.exists():
        settings = AppSettings()
        save_settings(settings)
        return settings

    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    defaults = asdict(AppSettings())
    defaults.update({k: v for k, v in data.items() if k in defaults})
    return AppSettings(**defaults)


def save_settings(settings: AppSettings) -> None:
    ensure_directories()
    SETTINGS_PATH.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
