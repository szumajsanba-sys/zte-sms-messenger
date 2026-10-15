from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from zte_sms.i18n import t
from zte_sms.models import AppSettings, SyncResult
from zte_sms.settings import EXPORT_DIR, RAW_DIR, ROOT_DIR, load_settings, save_settings
from zte_sms.storage import SmsStorage
from zte_sms.sync import SyncService
from .workers import SyncWorker


LIGHT_STYLE = """
QMainWindow, QWidget { background: #f8fafc; color: #0f172a; font-size: 13px; font-family: 'Segoe UI', system-ui, sans-serif; }
QLineEdit, QComboBox, QSpinBox, QTextEdit { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 10px; color: #0f172a; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #3b82f6; }
QListWidget { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #f1f5f9; }
QListWidget::item:hover { background: #f1f5f9; }
QListWidget::item:selected { background: #eff6ff; color: #1d4ed8; font-weight: 600; border-left: 3px solid #3b82f6; }
QPushButton { background: #2563eb; color: #ffffff; border: 0; border-radius: 8px; padding: 7px 14px; font-weight: 600; }
QPushButton:hover { background: #1d4ed8; }
QPushButton:disabled { background: #94a3b8; }
QToolBar { background: #ffffff; border-bottom: 1px solid #e2e8f0; spacing: 8px; padding: 4px 8px; }
QFrame#bubble { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px; border-top-left-radius: 4px; padding: 12px; }
QLabel#dateLabel { background: #e2e8f0; color: #475569; font-weight: 600; font-size: 11px; border-radius: 10px; padding: 3px 10px; }
QScrollBar:vertical { border: none; background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 4px; min-height: 20px; }
"""

DARK_STYLE = """
QMainWindow, QWidget { background: #0f172a; color: #f8fafc; font-size: 13px; font-family: 'Segoe UI', system-ui, sans-serif; }
QLineEdit, QComboBox, QSpinBox, QTextEdit { background: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; padding: 6px 10px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #60a5fa; }
QListWidget { background: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; }
QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #283548; }
QListWidget::item:hover { background: #283548; }
QListWidget::item:selected { background: #1e3a8a; color: #93c5fd; font-weight: 600; border-left: 3px solid #60a5fa; }
QPushButton { background: #3b82f6; color: #ffffff; border: 0; border-radius: 8px; padding: 7px 14px; font-weight: 600; }
QPushButton:hover { background: #2563eb; }
QPushButton:disabled { background: #475569; }
QToolBar { background: #1e293b; border-bottom: 1px solid #334155; spacing: 8px; padding: 4px 8px; }
QFrame#bubble { background: #1e293b; border: 1px solid #334155; border-radius: 14px; border-top-left-radius: 4px; padding: 12px; }
QLabel#dateLabel { background: #334155; color: #94a3b8; font-weight: 600; font-size: 11px; border-radius: 10px; padding: 3px 10px; }
QScrollBar:vertical { border: none; background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #475569; border-radius: 4px; min-height: 20px; }
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings: AppSettings = load_settings()
        self.storage = SmsStorage()
        self.current_sender_id: int | None = None
        self.thread: QThread | None = None
        self.worker: SyncWorker | None = None

        self.setWindowTitle(t("app_title", self.settings.language))
        self.resize(1180, 750)
        self.build_ui()
        self.apply_theme()
        self.retranslate_ui()
        self.load_chats()
        self.update_status(t("ready", self.settings.language))

        # Auto-sync timer: sync immediately on launch and then every 5 seconds
        self.auto_sync_timer = QTimer(self)
        self.auto_sync_timer.setInterval(5000)
        self.auto_sync_timer.timeout.connect(self.sync_now_quiet)
        self.auto_sync_timer.start()
        QTimer.singleShot(600, self.sync_now_quiet)

    def build_ui(self) -> None:
        # Toolbar
        self.toolbar = QToolBar("Main")
        self.addToolBar(self.toolbar)

        self.sync_action = QAction(self)
        self.sync_action.triggered.connect(self.sync_now)

        self.import_action = QAction(self)
        self.import_action.triggered.connect(self.import_json)

        self.cleanup_action = QAction(self)
        self.cleanup_action.triggered.connect(self.cleanup_saved)

        self.export_action = QAction(self)
        self.export_action.triggered.connect(self.export_all)

        self.folder_action = QAction(self)
        self.folder_action.triggered.connect(lambda: self.open_folder(RAW_DIR))

        self.web_action = QAction(self)
        self.web_action.triggered.connect(self.open_web_viewer)

        self.toolbar.addActions(
            [
                self.sync_action,
                self.import_action,
                self.cleanup_action,
                self.export_action,
                self.folder_action,
                self.web_action,
            ]
        )

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 8, 12, 12)

        # Settings panel
        self.settings_panel = QWidget()
        self.form = QFormLayout(self.settings_panel)
        self.form.setContentsMargins(0, 0, 0, 8)

        self.router_url = QLineEdit(self.settings.router_url)
        self.password = QLineEdit(self.settings.password)
        self.password.setEchoMode(QLineEdit.Password)

        self.mem_store = QComboBox()
        self.mem_store.addItems(["1 - Device", "2 - SIM"])
        self.mem_store.setCurrentIndex(0 if self.settings.mem_store == 1 else 1)

        self.timeout = QSpinBox()
        self.timeout.setRange(10, 180)
        self.timeout.setValue(self.settings.request_timeout)

        self.threshold = QSpinBox()
        self.threshold.setRange(1, 500)
        self.threshold.setValue(self.settings.cleanup_threshold)

        self.auto_cleanup = QCheckBox()
        self.auto_cleanup.setChecked(self.settings.auto_cleanup)

        self.safe_mode = QCheckBox()
        self.safe_mode.setChecked(self.settings.safe_mode)

        self.dry_run = QCheckBox()
        self.dry_run.setChecked(self.settings.dry_run_delete)

        self.theme = QComboBox()
        self.theme.addItems(["light", "dark"])
        self.theme.setCurrentText(self.settings.theme)

        self.language_box = QComboBox()
        self.language_box.addItems(["English (en)", "Русский (ru)"])
        self.language_box.setCurrentIndex(0 if self.settings.language == "en" else 1)
        self.language_box.currentIndexChanged.connect(self.on_language_changed)

        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(self.save_settings_from_ui)

        # Labels for translation
        self.lbl_router_url = QLabel()
        self.lbl_password = QLabel()
        self.lbl_mem_store = QLabel()
        self.lbl_timeout = QLabel()
        self.lbl_threshold = QLabel()
        self.lbl_theme = QLabel()
        self.lbl_language = QLabel()

        self.form.addRow(self.lbl_router_url, self.router_url)
        self.form.addRow(self.lbl_password, self.password)
        self.form.addRow(self.lbl_mem_store, self.mem_store)
        self.form.addRow(self.lbl_timeout, self.timeout)
        self.form.addRow(self.lbl_threshold, self.threshold)
        self.form.addRow("", self.auto_cleanup)
        self.form.addRow("", self.safe_mode)
        self.form.addRow("", self.dry_run)
        self.form.addRow(self.lbl_theme, self.theme)
        self.form.addRow(self.lbl_language, self.language_box)
        self.form.addRow("", self.save_btn)

        # Splitter: Sidebar + Chat
        splitter = QSplitter(Qt.Horizontal)

        # Left Column: Search, Filter, Chat List
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.textChanged.connect(self.load_chats)

        self.filter = QComboBox()
        self.filter.addItems(["All", "Unread", "Today", "Last 7 days"])
        self.filter.currentIndexChanged.connect(self.load_chats)

        self.chat_list = QListWidget()
        self.chat_list.currentItemChanged.connect(self.chat_selected)

        left_layout.addWidget(self.search)
        left_layout.addWidget(self.filter)
        left_layout.addWidget(self.chat_list, 1)

        # Right Column: Chat Header, Messages Scroll, Log
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self.chat_title = QLabel()
        self.chat_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.mark_read_btn = QPushButton()
        self.mark_read_btn.clicked.connect(self.mark_current_read)
        header.addWidget(self.chat_title, 1)
        header.addWidget(self.mark_read_btn)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.addStretch()
        self.scroll.setWidget(self.messages_container)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)

        right_layout.addLayout(header)
        right_layout.addWidget(self.scroll, 1)
        right_layout.addWidget(self.log)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        root_layout.addWidget(self.settings_panel)
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

    def retranslate_ui(self) -> None:
        lang = self.settings.language
        self.setWindowTitle(t("app_title", lang))
        self.sync_action.setText(t("sync", lang))
        self.import_action.setText(t("import_json", lang))
        self.cleanup_action.setText(t("cleanup", lang))
        self.export_action.setText(t("export", lang))
        self.folder_action.setText(t("backup_folder", lang))
        self.web_action.setText(t("open_web", lang))

        self.lbl_router_url.setText(t("router_url", lang))
        self.lbl_password.setText(t("password", lang))
        self.lbl_mem_store.setText(t("sms_storage", lang))
        self.lbl_timeout.setText(t("timeout", lang))
        self.lbl_threshold.setText(t("threshold", lang))
        self.auto_cleanup.setText(t("auto_cleanup", lang))
        self.safe_mode.setText(t("safe_mode", lang))
        self.dry_run.setText(t("dry_run", lang))
        self.lbl_theme.setText(t("theme", lang))
        self.lbl_language.setText(t("language", lang))
        self.save_btn.setText(t("save_settings", lang))

        self.search.setPlaceholderText(t("search_placeholder", lang))

        idx = self.filter.currentIndex()
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItems(
            [
                t("filter_all", lang),
                t("filter_unread", lang),
                t("filter_today", lang),
                t("filter_week", lang),
            ]
        )
        self.filter.setCurrentIndex(max(0, idx))
        self.filter.blockSignals(False)

        mem_idx = self.mem_store.currentIndex()
        self.mem_store.blockSignals(True)
        self.mem_store.clear()
        self.mem_store.addItems([t("mem_device", lang), t("mem_sim", lang)])
        self.mem_store.setCurrentIndex(max(0, mem_idx))
        self.mem_store.blockSignals(False)

        if not self.current_sender_id:
            self.chat_title.setText(t("select_chat", lang))
        self.mark_read_btn.setText(t("mark_read", lang))

    def on_language_changed(self) -> None:
        new_lang = "en" if self.language_box.currentIndex() == 0 else "ru"
        self.settings.language = new_lang
        save_settings(self.settings)
        self.retranslate_ui()
        self.load_chats()

    def apply_theme(self) -> None:
        QGuiApplication.instance().setStyleSheet(DARK_STYLE if self.settings.theme == "dark" else LIGHT_STYLE)

    def filter_mode(self) -> str:
        return ["all", "unread", "today", "week"][self.filter.currentIndex()]

    def load_chats(self) -> None:
        current = self.current_sender_id
        self.chat_list.clear()
        for row in self.storage.get_chats(self.search.text().strip(), self.filter_mode()):
            unread = f"  [{row['unread_count']}]" if row["unread_count"] else ""
            last_text = (row["last_text"] or "").replace("\n", " ")
            time_part = (row["last_at"] or "")[11:16] or (row["last_at"] or "")[:10]
            display = f"{row['display_name']}{unread}\n{time_part}  {last_text[:60]}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, int(row["id"]))
            self.chat_list.addItem(item)
            if current == int(row["id"]):
                self.chat_list.setCurrentItem(item)
        summary = t(
            "status_summary",
            self.settings.language,
            chats=self.chat_list.count(),
            total=self.storage.count_messages(),
        )
        self.update_status(summary)

    def chat_selected(self, current: QListWidgetItem | None) -> None:
        if not current:
            return
        self.current_sender_id = int(current.data(Qt.UserRole))
        title = current.text().split("\n", 1)[0]
        self.chat_title.setText(title)
        self.render_messages(self.current_sender_id)

    def clear_messages(self) -> None:
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def render_messages(self, sender_id: int) -> None:
        self.clear_messages()
        last_day = None
        lang = self.settings.language
        for row in self.storage.get_messages_for_sender(sender_id):
            day = (row["received_at"] or row["imported_at"] or "")[:10]
            if day != last_day:
                date_label = QLabel(day or t("no_date", lang))
                date_label.setObjectName("dateLabel")
                date_label.setAlignment(Qt.AlignCenter)
                self.messages_layout.addWidget(date_label)
                last_day = day

            bubble = QFrame()
            bubble.setObjectName("bubble")
            layout = QVBoxLayout(bubble)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(6)

            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            time_str = (row["received_at"] or row["imported_at"] or "")[11:16]
            time_label = QLabel(time_str)
            time_label.setStyleSheet("color: #94a3b8; font-size: 11px;")

            id_str = f"#{row['zte_id']}" if row["zte_id"] else ""
            id_label = QLabel(id_str)
            id_label.setStyleSheet("color: #64748b; font-size: 10px; font-family: monospace;")

            copy_btn = QPushButton(t("copy_text", lang))
            copy_btn.setStyleSheet("padding: 2px 8px; font-size: 11px; border-radius: 4px;")
            content_text = row["content_decoded"] or ""
            copy_btn.clicked.connect(lambda _, text=content_text: self.copy_to_clipboard(text))

            top_row.addWidget(id_label)
            top_row.addStretch()
            top_row.addWidget(time_label)
            top_row.addWidget(copy_btn)

            text = QLabel(content_text)
            text.setWordWrap(True)
            text.setOpenExternalLinks(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text.setStyleSheet("font-size: 13.5px; line-height: 1.4;")

            layout.addLayout(top_row)
            layout.addWidget(text)
            self.messages_layout.addWidget(bubble)
        self.messages_layout.addStretch()

    def copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.update_status(t("copied", self.settings.language))

    def save_settings_from_ui(self) -> None:
        self.settings.router_url = self.router_url.text().strip() or "http://192.168.0.1"
        self.settings.password = self.password.text()
        self.settings.mem_store = 1 if self.mem_store.currentIndex() == 0 else 2
        self.settings.request_timeout = self.timeout.value()
        self.settings.cleanup_threshold = self.threshold.value()
        self.settings.auto_cleanup = self.auto_cleanup.isChecked()
        self.settings.safe_mode = self.safe_mode.isChecked()
        self.settings.dry_run_delete = self.dry_run.isChecked()
        self.settings.theme = self.theme.currentText()
        self.settings.language = "en" if self.language_box.currentIndex() == 0 else "ru"
        save_settings(self.settings)
        self.apply_theme()
        self.retranslate_ui()
        self.update_status(t("settings_saved", self.settings.language))

    def sync_now_quiet(self) -> None:
        if self.thread is not None:
            return
        self.start_worker("router", quiet=True)

    def sync_now(self) -> None:
        self.save_settings_from_ui()
        self.start_worker("router", quiet=False)

    def import_json(self) -> None:
        lang = self.settings.language
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("select_json_title", lang),
            str(Path.cwd()),
            t("json_filter", lang),
        )
        if path:
            self.start_worker("file", path=path, quiet=False)

    def cleanup_saved(self) -> None:
        self.save_settings_from_ui()
        lang = self.settings.language
        saved_count = len(self.storage.router_saved_message_ids(self.settings.mem_store))
        if self.settings.dry_run_delete:
            text = t("cleanup_dry_run_prompt", lang, count=saved_count)
        else:
            text = t("cleanup_real_prompt", lang, count=saved_count)

        if QMessageBox.question(self, t("cleanup_title", lang), text) == QMessageBox.Yes:
            self.start_worker("cleanup", quiet=False)

    def start_worker(self, mode: str, path: str | None = None, quiet: bool = False) -> None:
        lang = self.settings.language
        if self.thread:
            if not quiet:
                QMessageBox.information(self, t("app_title", lang), t("operation_in_progress", lang))
            return
        self.is_quiet_worker = quiet
        self.thread = QThread()
        service = SyncService(self.settings, self.storage)
        self.worker = SyncWorker(service, mode, path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        if not quiet:
            self.worker.progress.connect(self.update_status)
        self.worker.finished.connect(self.worker_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker_thread_finished)
        self.thread.start()

    def worker_thread_finished(self) -> None:
        self.thread = None
        self.worker = None

    def worker_finished(self, result: SyncResult) -> None:
        lang = self.settings.language
        self.load_chats()
        if self.current_sender_id:
            self.render_messages(self.current_sender_id)
        if result.status == "ok":
            warning_text = "\n".join(result.warnings[:5])
            for detail in result.details:
                self.log.append(detail)
            msg = t(
                "sync_done",
                lang,
                found=result.messages_found,
                new=result.messages_new,
                deleted=result.messages_deleted_from_router,
            )
            self.update_status(msg)
            if result.warnings and not getattr(self, "is_quiet_worker", False):
                QMessageBox.warning(self, t("warnings_title", lang), warning_text)
        else:
            err = result.error or t("error", lang)
            self.update_status(f"{t('error', lang)}: {err}")
            if not getattr(self, "is_quiet_worker", False):
                QMessageBox.critical(self, t("error", lang), err)

    def mark_current_read(self) -> None:
        if self.current_sender_id:
            self.storage.mark_sender_read(self.current_sender_id)
            self.load_chats()
            self.render_messages(self.current_sender_id)

    def export_all(self) -> None:
        path = self.storage.export_all("csv")
        lang = self.settings.language
        self.update_status(t("export_status", lang, path=path))
        QMessageBox.information(self, t("export_title", lang), t("export_saved", lang, path=path))

    def open_web_viewer(self) -> None:
        web_file = ROOT_DIR / "web" / "index.html"
        if web_file.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(web_file)))
        else:
            standalone_file = ROOT_DIR / "standalone_viewer" / "index.html"
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(standalone_file)))

    def open_folder(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def update_status(self, message: str) -> None:
        self.statusBar().showMessage(message)
        self.log.append(message)
