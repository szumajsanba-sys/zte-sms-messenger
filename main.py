from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure UTF-8 output in Windows PowerShell/CMD
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from zte_sms.auto_sync import AutoSyncEngine
from zte_sms.server import create_server
from zte_sms.settings import LOG_DIR, ROOT_DIR, ensure_directories, load_settings
from zte_sms.storage import SmsStorage
from zte_sms.sync import SyncService


def configure_logging() -> None:
    ensure_directories()
    logging.basicConfig(
        filename=LOG_DIR / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def run_import(path: str) -> int:
    settings = load_settings()
    service = SyncService(settings, SmsStorage())
    result = service.import_from_file(path, print)
    if result.status != "ok":
        print(f"Error: {result.error}")
        return 1
    print(f"Done. Found: {result.messages_found}, New: {result.messages_new}")
    print(f"Raw backup: {result.raw_backup_path}")
    print(f"Decoded backup: {result.decoded_backup_path}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings[:20]:
            print(f"- {warning}")
    return 0


def run_gui() -> int:
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


def run_server_mode(port: int = 8080, open_browser: bool = True) -> int:
    settings = load_settings()
    storage = SmsStorage()

    # Start background Auto-sync: immediately and then every 5 seconds
    auto_sync = AutoSyncEngine(settings, storage, interval_seconds=5.0)
    auto_sync.start()

    # Create embedded HTTP Server
    httpd, actual_port = create_server(
        port=port,
        storage=storage,
        settings=settings,
        auto_sync=auto_sync,
    )

    url = f"http://127.0.0.1:{actual_port}/"

    print("=" * 64)
    print("  💬 ZTE SMS Live Messenger & Keeper (Standalone Server)")
    print(f"  🌐 Web Interface: {url}")
    print(f"  📶 Modem URL:     {settings.router_url}")
    print("  ⏱️  Auto-sync:     Active (immediate start + every 5 seconds)")
    print("=" * 64)
    print(f"Server is listening. Press Ctrl+C in this window to stop.\n")

    if open_browser:
        def _open() -> None:
            time.sleep(0.6)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping ZTE SMS Messenger...")
    finally:
        auto_sync.stop()
        httpd.server_close()
        print("Stopped cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ZTE SMS Live Messenger & Keeper - 4G Modem SMS Sync & Web Viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the Qt desktop GUI instead of the web server",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the web server without automatically opening the default browser",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for the embedded web server (default: 8080)",
    )
    parser.add_argument(
        "--import-file",
        help="Import a local sms_response.json without starting a server or GUI",
    )
    args = parser.parse_args()

    configure_logging()

    if args.import_file:
        return run_import(args.import_file)

    if args.gui:
        return run_gui()

    # Default mode: Live web server + Auto-sync (5s) + browser open
    return run_server_mode(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
