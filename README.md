# 💬 ZTE SMS Live Messenger & Keeper

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![GUI: PySide6](https://img.shields.io/badge/GUI-PySide6-41cd52.svg)](https://pypi.org/project/PySide6/)
[![Auto-Sync: 5s](https://img.shields.io/badge/Auto--Sync-Every_5s-10b981.svg)](web/index.html)
[![Standalone Executable](https://img.shields.io/badge/Release-Windows_x64-orange.svg)](release/ZTE-SMS-Messenger-Windows-x64.zip)

> 🚀 **The definitive fix for the infamous 10-year-old ZTE 4G modem bug** where the official web interface (`index.html#sms`) hangs forever on *"Waiting..."* / *"Ожидание..."*.

[English](#english) | [Русский](#русский)

---

<a name="english"></a>
## 🇬🇧 English

### Overview

Many ZTE 4G LTE USB dongles and Wi-Fi routers (such as **ZTE MF833T, MF833V, MF286D, MF920**, etc.) suffer from a stubborn firmware bug: when users open the SMS inbox in the web management portal, the screen gets permanently stuck on a loading spinner showing **"Waiting..."**.

The modem hardware actually receives and stores your SMS messages correctly, but the modem's built-in web script fails when rendering UTF-16 BE hex-encoded Cyrillic/multilingual messages.

**ZTE SMS Live Messenger** solves this problem permanently:
1. **Instant Auto-Sync on Launch & Continuous Sync Every 5 Seconds:** The app connects directly to your ZTE modem at `http://192.168.0.1`, pulls all incoming SMS immediately on startup, and automatically polls every 5 seconds in the background.
2. **Standalone Executable (No Python Needed):** Download and run `ZTE-SMS-Messenger.exe`. It runs on any Windows x64 computer without Python installed!
3. **High-End Web Messenger UI:** Automatically opens your default browser at `http://localhost:8080/` with a Telegram-style messenger interface.
4. **Real-Time Live Updates:** New SMS appear automatically in real-time without page refreshes.

---

### Key Features

- **5-Second Continuous Auto-Sync:** Never miss a verification code or 2FA SMS.
- **Works Without Python:** Pre-compiled standalone Windows release in `release/ZTE-SMS-Messenger-Windows-x64.zip`.
- **Live Modem Status Indicator:** Glowing green dot showing connection to `192.168.0.1` and live sync countdown.
- **Instant Decoding:** Converts hex UTF-16 BE, UTF-16 LE, UTF-8, and GSM-7 SMS into readable text.
- **Messenger Interface:** Telegram-style chat layout with sender avatars, date separators, formatted timestamps, copy buttons, and clickable links.
- **Multilingual UI:** Instant switch between **English** and **Russian**.
- **Dark & Light Themes:** Beautiful modern styling tailored for readability.
- **Automated Backup & Database:** Stores messages in `data/db/sms.sqlite3`, raw backups in `data/raw/`, and decoded backups in `data/decoded/`.
- **Excel-Friendly Export:** 1-click export to UTF-8 BOM CSV, JSON, and formatted TXT.

---

### ⚡ Quick Start: 2 Ways to Use

#### Method 1: Standalone Pre-compiled .EXE (Recommended for Users)
1. Download `ZTE-SMS-Messenger-Windows-x64.zip` from [Releases](release/ZTE-SMS-Messenger-Windows-x64.zip) and extract it.
2. Double-click **`ZTE-SMS-Messenger.exe`**.
3. It immediately syncs with your ZTE modem, keeps syncing every 5 seconds, and opens the Web Messenger in your browser!

#### Method 2: Run with Python Source
```powershell
git clone https://github.com/your-username/zte-sms-messenger.git
cd zte-sms-messenger

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Start Live Web Messenger (auto-syncs every 5s & opens browser)
python main.py

# Or launch Desktop Qt GUI
python main.py --gui
```

---

<a name="русский"></a>
## 🇷🇺 Русский

### Описание

На модемах и роутерах ZTE (например, **ZTE MF833T, MF833V, MF286D, MF920** и аналогичных) широко известна проблема: при попытке открыть раздел SMS веб-интерфейс (`index.html#sms`) уходит в вечное зависание с надписью **«Ожидание...»**.

Модем исправно принимает сообщения, но встроенный JavaScript веб-панели ломается при обработке сообщений в кодировке UTF-16 BE (hex-представление русского текста).

**ZTE SMS Live Messenger** полностью и навсегда решает эту проблему:
- **Автосинк при старте и каждые 5 секунд:** Программа сразу после запуска опрашивает модем по адресу `192.168.0.1` и каждые 5 секунд в фоновом режиме забирает новые SMS.
- **Работает на любом ПК без установки Python:** Скомпилирована в готовый бинарник `ZTE-SMS-Messenger.exe`.
- **Живой Веб-Мессенджер:** При запуске автоматически открывает в браузере стильный интерфейс мессенджера (как Telegram Web) со всеми диалогами.
- **Обновление на лету:** Новые SMS и коды подтверждения появляются в окне автоматически в реальном времени.

---

### Быстрый запуск

1. Скачайте архив релиза `release/ZTE-SMS-Messenger-Windows-x64.zip` и распакуйте.
2. Запустите файл **`ZTE-SMS-Messenger.exe`**.
3. Программа подключится к модему, начнет синхронизацию каждые 5 секунд и откроет веб-мессенджер в вашем браузере!

---

### Структура проекта

```text
├── release/                # Готовый скомпилированный релиз (ZIP архив для Windows x64)
├── run_web_server.bat      # Запуск сервера веб-мессенджера через Python
├── run_desktop.bat         # Запуск Qt GUI интерфейса
├── web/                    # Исходники живого веб-интерфейса
│   └── index.html
├── zte_sms/                # Логика ядра
│   ├── auto_sync.py        # Фоновый движок автосинка каждые 5 секунд
│   ├── server.py           # Встроенный HTTP сервер с REST API
│   ├── auth.py             # Авторизация ZTE (SHA256, Base64, MD5 AD токены)
│   ├── cleanup.py          # Пакетное удаление SMS с роутера
│   ├── client.py           # HTTP клиент к роутеру
│   ├── decoder.py          # Декодер UTF-16 BE / UCS-2 / GSM
│   ├── i18n.py             # Двуязычная локализация (EN / RU)
│   ├── models.py           # Модели данных
│   ├── settings.py         # Управление конфигурацией
│   ├── storage.py          # База данных SQLite и экспорт
│   └── sync.py             # Сервис синхронизации и бэкапов
├── ui/                     # Графический интерфейс PySide6
│   ├── main_window.py      # Главное окно с поддержкой автосинка
│   └── workers.py          # Фоновые потоки QThread
├── main.py                 # Главная точка входа (Web Server + AutoSync / GUI / CLI)
├── build_release.py        # Скрипт компиляции .exe через PyInstaller
├── MAIL_RU_ANSWER.md       # Готовый ответ для публикации на Ответах Mail.ru / 4PDA
├── requirements.txt        # Зависимости Python
├── LICENSE                 # Лицензия MIT
└── README.md
```

---

### Лицензия
Распространяется под свободной лицензией [MIT](LICENSE).
