# 💬 ZTE SMS Live Messenger & Keeper

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![GUI: PySide6](https://img.shields.io/badge/GUI-PySide6-41cd52.svg)](https://pypi.org/project/PySide6/)
[![Auto-Sync: 5s](https://img.shields.io/badge/Auto--Sync-Every_5s-10b981.svg)](web/index.html)
[![Windows Release](https://img.shields.io/badge/Release-Windows_x64-orange.svg)](release/ZTE-SMS-Messenger-Windows-x64.zip)

> 🌐 **Documentation Language / Язык:** [🇷🇺 Читать на русском (Основная версия - README.md)](README.md) | **English**

> 🚀 **The definitive fix for the infamous 10-year-old ZTE 4G modem bug** where the official web interface (`index.html#sms`) hangs forever on *"Waiting..."* / *"Ожидание..."*.

---

## 📌 Problem & Solution Overview

Many ZTE 4G LTE USB dongles and Wi-Fi routers (such as **ZTE MF833T, MF833V, MF286D, MF920, MF79U**, etc.) suffer from an unresolved firmware bug: when users attempt to open the SMS inbox in the web management portal, the page freezes permanently with an infinite spinner displaying **"Waiting..."**.

The modem hardware receives and stores SMS correctly in its internal memory, but the built-in web script crashes when decoding Cyrillic / multilingual UTF-16 BE Hex messages.

**ZTE SMS Live Messenger** permanently solves this:
1. **Instant Auto-Sync on Launch & Continuous Sync Every 5 Seconds:** The app connects directly to your ZTE modem at `http://192.168.0.1`, pulls all incoming SMS immediately on startup, and automatically polls every 5 seconds in the background.
2. **Standalone Executable (No Python Needed):** Pre-compiled standalone Windows executable `ZTE-SMS-Messenger.exe` that runs on any 64-bit Windows machine without Python installed.
3. **High-End Web Messenger UI:** Automatically opens your default browser with a clean, responsive Telegram-style web messenger.
4. **Real-Time Live Updates:** Incoming SMS and 2FA verification codes appear instantly without refreshing the page.

---

## ✨ Key Features

- ⏱️ **Continuous 5-Second Auto-Sync:** Never miss an authentication code or urgent SMS.
- 💻 **Runs Without Python:** Download the ready-to-run release archive `release/ZTE-SMS-Messenger-Windows-x64.zip`.
- 🛡️ **Router Memory Cleanup (100 SMS Limit Protection):** ZTE modems drop incoming SMS once the 100-SMS hardware limit is reached. The app:
  - Tracks modem memory usage in real time (`X/100 SMS`).
  - Warns at >50 (half-full) and >90 (almost full) messages.
  - Triggers a critical alert at 100/100 SMS.
  - Offers a 1-click cleanup button to free modem memory while **100% safely preserving every message in the local SQLite database**.
- 👁️ **Live Read/Unread Tracking:** Clicking any chat clears the unread badge and permanently persists `is_read=1` and `unread_count=0` to the SQLite database.
- 🌐 **Smart CIS Language Auto-Detection:** Automatically activates Russian for users with CIS browser locales (`ru`, `be`, `uk`, `kk`, `ky`, `tg`, etc.) and English for all other systems. Allows 1-click manual switching (Auto / RU / EN).
- 🌓 **Dark & Light Themes:** Modern aesthetics with 1-click toggle ☀️ / 🌙 in the top bar.
- 📶 **Live Connection Indicator:** Glowing pulse dot displaying real-time connection status to `192.168.0.1`.
- 🔤 **Smart Decoder:** Seamlessly handles UCS-2 / UTF-16 BE, UTF-16 LE, UTF-8, and 7-bit GSM encodings.
- 💾 **Automated Backups & SQLite:** Saves messages to `data/db/sms.sqlite3`, raw dumps to `data/backups/raw/`, and decoded archives to `data/backups/decoded/`.
- 📊 **Excel-Friendly Export:** 1-click export of complete message history to UTF-8 BOM CSV, JSON, or TXT.

---

## ⚡ Quick Start

### Method 1: Standalone .EXE (Recommended for Users)
1. Download [`release/ZTE-SMS-Messenger-Windows-x64.zip`](release/ZTE-SMS-Messenger-Windows-x64.zip) and extract it to any folder.
2. Double-click **`ZTE-SMS-Messenger.exe`**.
3. It connects to the modem, begins background sync every 5 seconds, and opens the Web Messenger at `http://localhost:8080/`.

### Method 2: Run with Python Source
```powershell
git clone https://github.com/your-username/zte-sms-messenger.git
cd zte-sms-messenger

# Setup virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Option A: Start Web Messenger (auto-sync 5s + opens browser)
python main.py

# Option B: Launch Desktop Qt GUI
python main.py --gui
```

Convenience batch files are also included:
* [`run_web_server.bat`](run_web_server.bat) — One-click launcher for Web Messenger.
* [`run_desktop.bat`](run_desktop.bat) — One-click launcher for PySide6 Desktop GUI.

---

## 📁 Repository Structure

```text
├── release/                # Pre-built Windows x64 release package (ZIP)
├── run_web_server.bat      # 1-click launcher for Web Messenger
├── run_desktop.bat         # 1-click launcher for PySide6 Desktop GUI
├── web/                    # Modern Web Messenger sources
│   └── index.html          # SPA with auto-sync, themes, router cleaner & language detection
├── standalone_viewer/      # Offline standalone HTML viewer
│   └── index.html
├── zte_sms/                # Core Python package
│   ├── auto_sync.py        # Background engine polling modem every 5 seconds
│   ├── server.py           # Embedded HTTP server with REST API
│   ├── cleanup.py          # Modem memory cleanup service
│   ├── auth.py             # ZTE modem authentication (SHA256, Base64, MD5 AD tokens)
│   ├── client.py           # HTTP client interacting with router endpoints
│   ├── decoder.py          # Multilingual SMS decoder (UTF-16 BE / UCS-2 / GSM)
│   ├── i18n.py             # Bilingual UI translations (EN / RU)
│   ├── models.py           # Dataclasses and settings schema
│   ├── settings.py         # Configuration loader/saver
│   ├── storage.py          # SQLite database layer and exporters
│   └── sync.py             # Backup and sync coordinator
├── ui/                     # Native Desktop GUI (PySide6)
│   ├── main_window.py      # Desktop GUI window with settings and filters
│   └── workers.py          # Background worker threads
├── main.py                 # Unified CLI/GUI/Web entry point
├── build_release.py        # PyInstaller build automation script
├── MAIL_RU_ANSWER.md       # Pre-written answer for forum users (Mail.ru, 4PDA)
├── requirements.txt        # Python dependencies
├── LICENSE                 # MIT License
├── README.md               # Russian documentation (default)
└── README_EN.md            # English documentation
```

---

## 📄 License
This project is open-source and released under the [MIT License](LICENSE).
