"""Localized Qt configuration, preview, recording browser, and service monitor."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .cameras import discover
from .config import AppConfig, load, save
from .i18n import Translator, format_datetime
from .runtime import companion_command
from .service import STATUS

LANGUAGES = (("en", "language.english"), ("ko", "language.korean"))
MODES = (("motion", "mode.motion"), ("continuous", "mode.continuous"), ("manual", "mode.manual"))


class FirstRunDialog(QDialog):
    """Language-first legal notice shown before initial configuration."""

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.trn = Translator(cfg.language)
        layout = QVBoxLayout(self)
        self.language = QComboBox()
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setMinimumWidth(480)
        self.accept_button = QPushButton()
        self.accept_button.clicked.connect(self.accept)
        self.language.currentIndexChanged.connect(self.retranslate)
        layout.addWidget(self.language)
        layout.addWidget(self.notice)
        layout.addWidget(self.accept_button)
        self.retranslate(initial=True)

    def retranslate(self, _index: int = 0, *, initial: bool = False) -> None:
        if initial:
            self.language.blockSignals(True)
            for code, key in LANGUAGES:
                self.language.addItem(self.trn.tr(key), code)
            self.language.setCurrentIndex(max(0, self.language.findData(self.cfg.language)))
            self.language.blockSignals(False)
        self.cfg.language = str(self.language.currentData() or self.cfg.language)
        self.trn = Translator(self.cfg.language)
        self.setWindowTitle(self.trn.tr("setup.title"))
        self.notice.setText(
            self.trn.tr("setup.notice") + "\n\n" + self.trn.tr("setup.choose_language")
        )
        self.accept_button.setText(self.trn.tr("setup.continue"))
        self.accept_button.setAccessibleName(self.accept_button.text())

    def accept(self) -> None:
        self.cfg.first_run_complete = True
        save(self.cfg)
        super().accept()


class Window(QMainWindow):
    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.trn = Translator(cfg.language)
        self.cap = None
        self.resize(1080, 720)
        root = QWidget()
        outer = QHBoxLayout(root)
        left = QVBoxLayout()
        self.settings_box = QGroupBox()
        form = QFormLayout(self.settings_box)
        self.language = QComboBox()
        self.camera = QComboBox()
        self.mode = QComboBox()
        self.directory = QLineEdit(cfg.storage.directory)
        self.browse = QPushButton()
        self.browse.clicked.connect(self.choose)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.directory, 1)
        folder_row.addWidget(self.browse)
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(cfg.storage.retention_days)
        self.save_button = QPushButton()
        self.save_button.clicked.connect(self.save_settings)
        self.language_row = form.rowCount()
        form.addRow("", self.language)
        self.camera_row = form.rowCount()
        form.addRow("", self.camera)
        self.mode_row = form.rowCount()
        form.addRow("", self.mode)
        self.folder_row = form.rowCount()
        form.addRow("", folder_row)
        self.days_row = form.rowCount()
        form.addRow("", self.days)
        form.addRow(self.save_button)
        self.form = form
        self.controls = QHBoxLayout()
        self.control_buttons: list[tuple[QPushButton, str]] = []
        for command in ("start", "stop", "restart"):
            button = QPushButton()
            button.clicked.connect(lambda _, value=command: self.command(value))
            self.controls.addWidget(button)
            self.control_buttons.append((button, command))
        self.status = QLabel()
        self.status.setWordWrap(True)
        left.addWidget(self.settings_box)
        left.addLayout(self.controls)
        left.addWidget(self.status)
        self.recordings_box = QGroupBox()
        recordings_layout = QVBoxLayout(self.recordings_box)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.refresh_button = QPushButton()
        self.search.textChanged.connect(self.refresh_recordings)
        self.refresh_button.clicked.connect(self.refresh_recordings)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.refresh_button)
        self.recordings = QListWidget()
        recordings_layout.addLayout(search_row)
        recordings_layout.addWidget(self.recordings)
        left.addWidget(self.recordings_box, 1)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(560, 420)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("background:#111;color:#ddd;padding:12px")
        outer.addLayout(left, 1)
        outer.addWidget(self.preview, 2)
        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)
        self.language.currentIndexChanged.connect(self.change_language)
        self.camera.currentIndexChanged.connect(self.open_camera)
        self.tray = QSystemTrayIcon(QIcon.fromTheme("camera-video"), self)
        self.tray.activated.connect(self.tray_activated)
        self.retranslate(rebuild=True)
        self.open_camera()
        self.tray.show()

    def retranslate(self, *, rebuild: bool = False) -> None:
        self.trn = Translator(self.cfg.language)
        self.setWindowTitle(self.trn.tr("app.title"))
        if rebuild:
            self.language.blockSignals(True)
            self.language.clear()
            for code, key in LANGUAGES:
                self.language.addItem(self.trn.tr(key), code)
            self.language.setCurrentIndex(max(0, self.language.findData(self.cfg.language)))
            self.language.blockSignals(False)
            self.camera.blockSignals(True)
            self.camera.clear()
            for item in discover(language=self.cfg.language):
                self.camera.addItem(
                    f"{item['name']} — {item['width']}×{item['height']}", item["index"]
                )
            self.camera.setCurrentIndex(max(0, self.camera.findData(self.cfg.camera.device)))
            self.camera.blockSignals(False)
            self.mode.blockSignals(True)
            self.mode.clear()
            for code, key in MODES:
                self.mode.addItem(self.trn.tr(key), code)
            self.mode.setCurrentIndex(max(0, self.mode.findData(self.cfg.mode)))
            self.mode.blockSignals(False)
        self.settings_box.setTitle(self.trn.tr("settings.group"))
        labels = (
            (self.language_row, "language.label"),
            (self.camera_row, "settings.camera"),
            (self.mode_row, "settings.recording_mode"),
            (self.folder_row, "settings.recording_folder"),
            (self.days_row, "settings.retention_days"),
        )
        for row, key in labels:
            self.form.itemAt(row, QFormLayout.ItemRole.LabelRole).widget().setText(self.trn.tr(key))
        self.browse.setText(self.trn.tr("common.browse"))
        self.save_button.setText(self.trn.tr("settings.save"))
        for button, command in self.control_buttons:
            button.setText(self.trn.tr(f"service.{command}"))
        self.preview.setText(self.trn.tr("camera.preview"))
        self.recordings_box.setTitle(self.trn.tr("recordings.group"))
        self.search.setPlaceholderText(self.trn.tr("recordings.search"))
        self.refresh_button.setText(self.trn.tr("recordings.refresh"))
        for widget in (
            self.language,
            self.camera,
            self.mode,
            self.directory,
            self.days,
            self.search,
        ):
            widget.setAccessibleName(
                self.trn.tr("language.label")
                if widget is self.language
                else widget.toolTip() or self.settings_box.title()
            )
        self.build_tray_menu()
        self.refresh_recordings()

    def change_language(self) -> None:
        code = self.language.currentData()
        if code and code != self.cfg.language:
            self.cfg.language = str(code)
            save(self.cfg)
            self.retranslate(rebuild=True)

    def build_tray_menu(self) -> None:
        menu = QMenu()
        open_action = QAction(self.trn.tr("tray.open"), menu)
        open_action.triggered.connect(self.show_normal)
        menu.addAction(open_action)
        for command in ("start", "stop", "restart"):
            action = QAction(self.trn.tr(f"service.{command}"), menu)
            action.triggered.connect(lambda _, value=command: self.command(value))
            menu.addAction(action)
        menu.addSeparator()
        quit_action = QAction(self.trn.tr("tray.quit"), menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(self.trn.tr("tray.status"))

    def open_camera(self) -> None:
        if self.cap:
            self.cap.release()
        data = self.camera.currentData()
        self.cap = cv2.VideoCapture(data) if data is not None else None

    def tick(self) -> None:
        if self.cap and self.cap.isOpened():
            ok, frame = self.cap.read()
            if ok:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channels = rgb.shape
                image = QImage(
                    rgb.data, width, height, channels * width, QImage.Format.Format_RGB888
                ).copy()
                self.preview.setPixmap(
                    QPixmap.fromImage(image).scaled(
                        self.preview.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        try:
            data = json.loads(STATUS.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"running": False}
        self.status.setText(
            self.trn.tr(
                "service.status",
                service=self.trn.tr("status.running" if data.get("running") else "status.stopped"),
                camera=self.trn.tr(
                    "status.connected" if data.get("camera_connected") else "status.unavailable"
                ),
                recording=self.trn.tr(
                    "status.recording" if data.get("recording") else "status.idle"
                ),
            )
        )

    def refresh_recordings(self) -> None:
        self.recordings.clear()
        query = self.search.text().casefold()
        root = Path(self.directory.text()).expanduser()
        for metadata in sorted(root.rglob("*.json"), reverse=True)[:250] if root.exists() else []:
            try:
                data = json.loads(metadata.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            searchable = f"{data.get('camera', '')} {data.get('event', '')}".casefold()
            if query and query not in searchable:
                continue
            event = self.trn.tr(f"event.{data.get('event', 'manual')}")
            date = format_datetime(
                float(data.get("started", metadata.stat().st_mtime)),
                self.cfg.language,
                self.cfg.date_time_format or None,
            )
            self.recordings.addItem(
                self.trn.tr(
                    "recordings.item", date=date, camera=data.get("camera", ""), event=event
                )
            )
        if not self.recordings.count():
            self.recordings.addItem(self.trn.tr("recordings.none"))

    def choose(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, self.trn.tr("settings.recording_folder"), self.directory.text()
        )
        if path:
            self.directory.setText(path)

    def save_settings(self) -> None:
        try:
            if self.camera.currentData() is not None:
                self.cfg.camera.device = int(self.camera.currentData())
            self.cfg.mode = str(self.mode.currentData())
            self.cfg.storage.directory = self.directory.text()
            self.cfg.storage.retention_days = self.days.value()
            path = save(self.cfg)
            QMessageBox.information(
                self, self.trn.tr("settings.saved_title"), self.trn.tr("settings.saved", path=path)
            )
        except Exception as exc:
            QMessageBox.critical(self, self.trn.tr("settings.invalid_title"), str(exc))

    def command(self, command: str) -> None:
        subprocess.Popen(
            [
                *companion_command("WebcamCCTV-CLI", "webcamcctv.cli"),
                "--language",
                self.cfg.language,
                command,
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if command == "start":
            self.tray.showMessage(
                self.trn.tr("tray.started_title"), self.trn.tr("tray.started_body")
            )

    def show_normal(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_normal()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.cap:
            self.cap.release()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("WebcamCCTV")
    app.setQuitOnLastWindowClosed(False)
    cfg = load()
    if not cfg.first_run_complete and FirstRunDialog(cfg).exec() != QDialog.DialogCode.Accepted:
        return 0
    window = Window(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
