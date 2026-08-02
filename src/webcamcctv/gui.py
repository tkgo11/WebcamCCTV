"""Polished localized Qt dashboard, preview, recordings, and service monitor."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from itertools import pairwise
from pathlib import Path

import cv2
from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QIcon,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .cameras import discover
from .config import AppConfig, load, save
from .gui_theme import THEMES, resolve_theme, stylesheet
from .i18n import Translator, format_datetime
from .runtime import companion_command
from .state import read_status, service_running

LANGUAGES = (("en", "language.english"), ("ko", "language.korean"))
MODES = (("motion", "mode.motion"), ("continuous", "mode.continuous"), ("manual", "mode.manual"))
THEME_OPTIONS = (("system", "theme.system"), ("dark", "theme.dark"), ("light", "theme.light"))
CONTROLS = (
    ("start", "service.start"),
    ("stop", "service.stop"),
    ("restart", "service.restart"),
    ("record-start", "recording.start"),
    ("record-stop", "recording.stop"),
)


def _system_is_dark() -> bool:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return True
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return app.palette().window().color().lightness() < 128


def apply_app_theme(preference: str) -> str:
    """Apply a resolved central theme and return its concrete name."""
    name = resolve_theme(preference, system_is_dark=_system_is_dark())
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setStyleSheet(stylesheet(name))
    return name


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _icon(name: str, color: str = "#94A3B8") -> QIcon:
    """Draw small scalable line icons without platform-specific font glyphs."""
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if name == "camera":
        painter.drawRoundedRect(QRectF(8, 14, 29, 22), 5, 5)
        painter.drawEllipse(QPointF(22.5, 25), 6, 6)
        painter.drawLine(37, 21, 43, 17)
        painter.drawLine(43, 17, 43, 33)
        painter.drawLine(43, 33, 37, 29)
    elif name == "play":
        painter.drawEllipse(QPointF(24, 24), 17, 17)
        painter.drawLine(21, 17, 21, 31)
        painter.drawLine(21, 17, 32, 24)
        painter.drawLine(32, 24, 21, 31)
    elif name == "stop":
        painter.drawEllipse(QPointF(24, 24), 17, 17)
        painter.drawRoundedRect(QRectF(18, 18, 12, 12), 2, 2)
    elif name == "restart":
        painter.drawArc(QRectF(9, 9, 30, 30), 35 * 16, 280 * 16)
        painter.drawLine(35, 8, 39, 17)
        painter.drawLine(39, 17, 29, 17)
    elif name == "record":
        painter.drawEllipse(QPointF(24, 24), 12, 12)
    elif name == "folder":
        painter.drawRoundedRect(QRectF(6, 14, 36, 25), 4, 4)
        painter.drawLine(8, 14, 19, 14)
        painter.drawLine(19, 14, 23, 19)
        painter.drawLine(23, 19, 41, 19)
    elif name == "refresh":
        painter.drawArc(QRectF(10, 10, 28, 28), 45 * 16, 270 * 16)
        painter.drawLine(33, 8, 39, 15)
        painter.drawLine(39, 15, 30, 17)
    elif name == "save":
        painter.drawRoundedRect(QRectF(9, 7, 30, 34), 3, 3)
        painter.drawRect(QRectF(15, 8, 17, 10))
        painter.drawRoundedRect(QRectF(15, 27, 18, 13), 2, 2)
    else:
        painter.drawEllipse(QPointF(21, 21), 11, 11)
        painter.drawLine(29, 29, 39, 39)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class Card(QWidget):
    """Reusable surfaced section with a compact heading."""

    def __init__(self, title: str = "", subtitle: str = "") -> None:
        super().__init__()
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 18)
        self.body.setSpacing(12)
        self.heading = QLabel(title)
        self.heading.setProperty("role", "sectionTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setProperty("role", "muted")
        self.subtitle.setWordWrap(True)
        self.body.addWidget(self.heading)
        self.body.addWidget(self.subtitle)


class StatusPill(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("status", True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_state("neutral", "—")

    def set_state(self, state: str, text: str) -> None:
        if self.property("state") != state:
            self.setProperty("state", state)
            _repolish(self)
        self.setText(text)


class FirstRunDialog(QDialog):
    """Language-first legal notice shown before initial configuration."""

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.trn = Translator(cfg.language)
        self.setObjectName("setupDialog")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(22)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(_icon("camera", THEMES[apply_app_theme(cfg.theme)].accent).pixmap(48, 48))
        titles = QVBoxLayout()
        self.brand_title = QLabel("WebcamCCTV")
        self.brand_title.setObjectName("brandTitle")
        self.brand_subtitle = QLabel()
        self.brand_subtitle.setProperty("role", "muted")
        titles.addWidget(self.brand_title)
        titles.addWidget(self.brand_subtitle)
        brand.addWidget(logo)
        brand.addLayout(titles, 1)
        layout.addLayout(brand)

        card = Card()
        card.heading.hide()
        card.subtitle.hide()
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setMinimumWidth(460)
        self.language = QComboBox()
        self.language.setAccessibleName("Language")
        card.body.addWidget(self.notice)
        card.body.addSpacing(4)
        card.body.addWidget(self.language)
        layout.addWidget(card)
        self.accept_button = QPushButton()
        self.accept_button.setProperty("variant", "primary")
        self.accept_button.setIcon(_icon("play", "#FFFFFF"))
        self.accept_button.clicked.connect(self.accept)
        self.language.currentIndexChanged.connect(self.retranslate)
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
        self.brand_subtitle.setText(self.trn.tr("app.subtitle"))
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
        self.cap: cv2.VideoCapture | None = None
        self.last_state_check = 0.0
        self.service_data: dict[str, object] = {"running": False}
        self._status_animation: QPropertyAnimation | None = None
        self._last_status_text = ""
        self.resize(1380, 860)
        self.setMinimumSize(980, 660)

        root = QWidget()
        root.setObjectName("appRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 24)
        outer.setSpacing(18)
        outer.addLayout(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_preview_card())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([410, 930])
        outer.addWidget(splitter, 1)
        self.setCentralWidget(root)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(max(16, int(1000 / cfg.preview_fps)))
        self.language.currentIndexChanged.connect(self.change_language)
        self.theme.currentIndexChanged.connect(self.change_theme)
        self.camera.currentIndexChanged.connect(self.open_camera)
        self.mode.currentIndexChanged.connect(self.update_controls)

        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.styleHints().colorSchemeChanged.connect(self._system_theme_changed)
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QSystemTrayIcon(_icon("camera", THEMES["dark"].accent), self)
        self.tray.activated.connect(self.tray_activated)
        self._install_shortcuts()
        self._set_tab_order()
        self.retranslate(rebuild=True)
        self.apply_theme()
        self.open_camera()
        if self.tray_available:
            self.tray.show()

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(_icon("camera", THEMES["dark"].accent).pixmap(46, 46))
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.brand_title = QLabel("WebcamCCTV")
        self.brand_title.setObjectName("brandTitle")
        self.brand_subtitle = QLabel()
        self.brand_subtitle.setProperty("role", "muted")
        titles.addWidget(self.brand_title)
        titles.addWidget(self.brand_subtitle)
        header.addWidget(logo)
        header.addLayout(titles)
        header.addStretch()
        self.global_status = StatusPill()
        header.addWidget(self.global_status)
        self.theme_label = QLabel()
        self.theme_label.setProperty("role", "muted")
        header.addWidget(self.theme_label)
        self.theme = QComboBox()
        self.theme.setMinimumWidth(128)
        self.theme.setAccessibleName("Theme")
        header.addWidget(self.theme)
        return header

    def _build_sidebar(self) -> QWidget:
        container = QWidget()
        container.setMinimumWidth(365)
        container.setMaximumWidth(470)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(14)

        self.service_card = Card()
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(8)
        status_grid.setVerticalSpacing(6)
        self.service_label = QLabel()
        self.camera_label = QLabel()
        self.recording_label = QLabel()
        for label in (self.service_label, self.camera_label, self.recording_label):
            label.setProperty("role", "muted")
        self.service_pill = StatusPill()
        self.camera_pill = StatusPill()
        self.recording_pill = StatusPill()
        for row, pair in enumerate(
            (
                (self.service_label, self.service_pill),
                (self.camera_label, self.camera_pill),
                (self.recording_label, self.recording_pill),
            )
        ):
            status_grid.addWidget(pair[0], row, 0)
            status_grid.addWidget(pair[1], row, 1)
        status_grid.setColumnStretch(0, 1)
        self.service_card.body.addLayout(status_grid)

        controls = QGridLayout()
        controls.setSpacing(8)
        self.controls = controls
        self.control_buttons: list[tuple[QPushButton, str]] = []
        icon_names = {
            "start": "play",
            "stop": "stop",
            "restart": "restart",
            "record-start": "record",
            "record-stop": "stop",
        }
        for index, (command, _key) in enumerate(CONTROLS):
            button = QPushButton()
            icon_color = "#FFFFFF" if command in {"start", "record-start"} else "#94A3B8"
            button.setIcon(_icon(icon_names[command], icon_color))
            button.setProperty("compact", True)
            if command == "start":
                button.setProperty("variant", "primary")
            elif command == "stop":
                button.setProperty("variant", "danger")
            elif command == "record-start":
                button.setProperty("variant", "record")
            button.clicked.connect(lambda _, value=command: self.command(value))
            row = 0 if index < 3 else 1
            column = index if index < 3 else (index - 3) * 2
            span = 1 if row == 0 else 2
            controls.addWidget(button, row, column, 1, span)
            self.control_buttons.append((button, command))
        self.service_card.body.addLayout(controls)
        self.status = QLabel()
        self.status.setProperty("role", "muted")
        self.status.setWordWrap(True)
        self.service_card.body.addWidget(self.status)
        layout.addWidget(self.service_card)

        self.settings_box = Card()
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.language = QComboBox()
        self.camera = QComboBox()
        self.mode = QComboBox()
        self.directory = QLineEdit(self.cfg.storage.directory)
        self.browse = QPushButton()
        self.browse.setIcon(_icon("folder"))
        self.browse.setProperty("compact", True)
        self.browse.clicked.connect(self.choose)
        folder = QWidget()
        folder_row = QHBoxLayout(folder)
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.setSpacing(8)
        folder_row.addWidget(self.directory, 1)
        folder_row.addWidget(self.browse)
        self.days = QSpinBox()
        self.days.setRange(1, 3650)
        self.days.setValue(self.cfg.storage.retention_days)
        self.save_button = QPushButton()
        self.save_button.setIcon(_icon("save"))
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self.save_settings)
        self.language_row = form.rowCount()
        form.addRow("", self.language)
        self.camera_row = form.rowCount()
        form.addRow("", self.camera)
        self.mode_row = form.rowCount()
        form.addRow("", self.mode)
        self.folder_row = form.rowCount()
        form.addRow("", folder)
        self.days_row = form.rowCount()
        form.addRow("", self.days)
        form.addRow(self.save_button)
        self.form = form
        self.settings_box.body.addLayout(form)
        layout.addWidget(self.settings_box)

        self.recordings_box = Card()
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search = QLineEdit()
        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(_icon("refresh"))
        self.refresh_button.setProperty("compact", True)
        self.search.textChanged.connect(self.refresh_recordings)
        self.refresh_button.clicked.connect(self.refresh_recordings)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(self.refresh_button)
        self.recordings = QListWidget()
        self.recordings.setMinimumHeight(150)
        self.recordings_box.body.addLayout(search_row)
        self.recordings_box.body.addWidget(self.recordings)
        layout.addWidget(self.recordings_box, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(container)
        return scroll

    def _build_preview_card(self) -> QWidget:
        card = Card()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_header = QHBoxLayout()
        self.preview_title = QLabel()
        self.preview_title.setProperty("role", "sectionTitle")
        self.preview_state = StatusPill()
        preview_header.addWidget(self.preview_title)
        preview_header.addStretch()
        preview_header.addWidget(self.preview_state)
        card.body.insertLayout(0, preview_header)
        card.heading.hide()
        card.subtitle.hide()
        surface = QWidget()
        surface.setObjectName("previewSurface")
        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(2, 2, 2, 2)
        self.preview = QLabel()
        self.preview.setObjectName("cameraPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(500, 390)
        self.preview.setWordWrap(True)
        surface_layout.addWidget(self.preview)
        card.body.addWidget(surface, 1)
        self.preview_hint = QLabel()
        self.preview_hint.setProperty("role", "muted")
        self.preview_hint.setWordWrap(True)
        card.body.addWidget(self.preview_hint)
        return card

    def _install_shortcuts(self) -> None:
        actions = (
            ("Ctrl+S", self.save_settings),
            ("Ctrl+F", self.search.setFocus),
            ("Ctrl+R", self.refresh_recordings),
        )
        for shortcut, slot in actions:
            action = QAction(self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            self.addAction(action)

    def _set_tab_order(self) -> None:
        chain = (
            self.theme,
            self.control_buttons[0][0],
            self.control_buttons[1][0],
            self.control_buttons[2][0],
            self.control_buttons[3][0],
            self.control_buttons[4][0],
            self.language,
            self.camera,
            self.mode,
            self.directory,
            self.browse,
            self.days,
            self.save_button,
            self.search,
            self.refresh_button,
            self.recordings,
        )
        for current, following in pairwise(chain):
            self.setTabOrder(current, following)

    def apply_theme(self) -> None:
        apply_app_theme(self.cfg.theme)
        _repolish(self.centralWidget())

    def _system_theme_changed(self, *_args: object) -> None:
        if self.cfg.theme == "system":
            self.apply_theme()

    def change_theme(self) -> None:
        preference = self.theme.currentData()
        if preference and preference != self.cfg.theme:
            self.cfg.theme = str(preference)
            self.apply_theme()
            try:
                save(self.cfg)
            except (OSError, ValueError, TypeError):
                pass

    def retranslate(self, *, rebuild: bool = False) -> None:
        self.trn = Translator(self.cfg.language)
        self.setWindowTitle(self.trn.tr("app.title"))
        self.brand_subtitle.setText(self.trn.tr("app.subtitle"))
        if rebuild:
            self.language.blockSignals(True)
            self.language.clear()
            for code, key in LANGUAGES:
                self.language.addItem(self.trn.tr(key), code)
            self.language.setCurrentIndex(max(0, self.language.findData(self.cfg.language)))
            self.language.blockSignals(False)
            self.theme.blockSignals(True)
            self.theme.clear()
            for code, key in THEME_OPTIONS:
                self.theme.addItem(self.trn.tr(key), code)
            self.theme.setCurrentIndex(max(0, self.theme.findData(self.cfg.theme)))
            self.theme.blockSignals(False)
            self.camera.blockSignals(True)
            self.camera.clear()
            for camera_data in discover(language=self.cfg.language):
                self.camera.addItem(
                    f"{camera_data['name']} — {camera_data['width']}×{camera_data['height']}",
                    camera_data["index"],
                )
            self.camera.setCurrentIndex(max(0, self.camera.findData(self.cfg.camera.device)))
            self.camera.blockSignals(False)
            self.mode.blockSignals(True)
            self.mode.clear()
            for code, key in MODES:
                self.mode.addItem(self.trn.tr(key), code)
            self.mode.setCurrentIndex(max(0, self.mode.findData(self.cfg.mode)))
            self.mode.blockSignals(False)

        self.theme_label.setText(self.trn.tr("app.theme"))
        self.service_card.heading.setText(self.trn.tr("service.group"))
        self.service_card.subtitle.setText(self.trn.tr("service.subtitle"))
        self.settings_box.heading.setText(self.trn.tr("settings.group"))
        self.settings_box.subtitle.setText(self.trn.tr("settings.subtitle"))
        self.recordings_box.heading.setText(self.trn.tr("recordings.group"))
        self.recordings_box.subtitle.setText(self.trn.tr("recordings.subtitle"))
        self.service_label.setText(self.trn.tr("dashboard.service"))
        self.camera_label.setText(self.trn.tr("dashboard.camera"))
        self.recording_label.setText(self.trn.tr("dashboard.recording"))
        labels = (
            (self.language_row, "language.label"),
            (self.camera_row, "settings.camera"),
            (self.mode_row, "settings.recording_mode"),
            (self.folder_row, "settings.recording_folder"),
            (self.days_row, "settings.retention_days"),
        )
        for row, key in labels:
            item = self.form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QLabel):
                widget.setText(self.trn.tr(key))
        self.browse.setText(self.trn.tr("common.browse"))
        self.save_button.setText(self.trn.tr("settings.save"))
        control_labels = dict(CONTROLS)
        for button, command in self.control_buttons:
            button.setText(self.trn.tr(control_labels[command]))
            button.setAccessibleName(button.text())
        if self.preview.pixmap() is None:
            self.preview.setText(self.trn.tr("camera.preview"))
        self.preview_title.setText(self.trn.tr("camera.preview"))
        self.preview_hint.setText(self.trn.tr("camera.preview_hint"))
        self.search.setPlaceholderText(self.trn.tr("recordings.search"))
        self.refresh_button.setText(self.trn.tr("recordings.refresh"))
        self.language.setAccessibleName(self.trn.tr("language.label"))
        self.camera.setAccessibleName(self.trn.tr("settings.camera"))
        self.mode.setAccessibleName(self.trn.tr("settings.recording_mode"))
        self.directory.setAccessibleName(self.trn.tr("settings.recording_folder"))
        self.days.setAccessibleName(self.trn.tr("settings.retention_days"))
        self.search.setAccessibleName(self.trn.tr("recordings.search"))
        self.build_tray_menu()
        self._update_status_widgets(self.service_data)
        self.update_controls()
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
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(self.trn.tr("tray.status"))

    def open_camera(self) -> None:
        if self.cap:
            self.cap.release()
        data = self.camera.currentData()
        if service_running():
            self.cap = None
            self.preview.clear()
            self.preview.setText(self.trn.tr("camera.preview_paused"))
            self.preview_state.set_state("warning", self.trn.tr("preview.paused"))
        else:
            self.cap = cv2.VideoCapture(data) if data is not None else None
            self.preview_state.set_state("good", self.trn.tr("preview.live"))

    def update_controls(self, _index: int = 0) -> None:
        manual = self.mode.currentData() == "manual"
        running = bool(self.service_data.get("running"))
        for button, command in self.control_buttons:
            if command.startswith("record-"):
                button.setEnabled(manual and running)

    def _fade_status(self) -> None:
        effect = self.status.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.status)
            self.status.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(220)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._status_animation = animation
        animation.start()

    def _update_status_widgets(self, data: dict[str, object]) -> None:
        running = bool(data.get("running"))
        connected = bool(data.get("camera_connected"))
        recording = bool(data.get("recording"))
        service_text = self.trn.tr("status.running" if running else "status.stopped")
        camera_text = self.trn.tr("status.connected" if connected else "status.unavailable")
        recording_text = self.trn.tr("status.recording" if recording else "status.idle")
        self.service_pill.set_state("good" if running else "neutral", service_text)
        self.global_status.set_state("good" if running else "neutral", service_text)
        self.camera_pill.set_state("good" if connected else "warning", camera_text)
        self.recording_pill.set_state("danger" if recording else "neutral", recording_text)
        detail = self.trn.tr(
            "service.status", service=service_text, camera=camera_text, recording=recording_text
        )
        if detail != self._last_status_text:
            self._last_status_text = detail
            self.status.setText(detail)
            self._fade_status()

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
                self.preview_state.set_state("good", self.trn.tr("preview.live"))
        now = time.monotonic()
        if now - self.last_state_check < 0.5:
            return
        self.last_state_check = now
        data = self.service_data = read_status()
        self.update_controls()
        if data.get("running") and self.cap is not None:
            self.cap.release()
            self.cap = None
            self.preview.clear()
            self.preview.setText(self.trn.tr("camera.preview_paused"))
            self.preview_state.set_state("warning", self.trn.tr("preview.paused"))
        elif not data.get("running") and self.cap is None and self.isVisible():
            self.open_camera()
        self._update_status_widgets(data)

    def refresh_recordings(self) -> None:
        self.recordings.clear()
        query = self.search.text().casefold()
        root = Path(self.directory.text()).expanduser()
        metadata_files = sorted(root.rglob("*.json"), reverse=True)[:250] if root.exists() else []
        for metadata in metadata_files:
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
            self.update_controls()
            QMessageBox.information(
                self, self.trn.tr("settings.saved_title"), self.trn.tr("settings.saved", path=path)
            )
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, self.trn.tr("settings.invalid_title"), str(exc))

    def command(self, command: str) -> None:
        if command in {"start", "restart"} and self.cap is not None:
            self.cap.release()
            self.cap = None
        try:
            subprocess.Popen(
                [
                    *companion_command("WebcamCCTV-CLI", "webcamcctv.cli"),
                    "--language",
                    self.cfg.language,
                    command,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            QMessageBox.critical(self, self.trn.tr("service.command_failed"), str(exc))
            return
        if command == "start":
            self.tray.showMessage(
                self.trn.tr("tray.started_title"), self.trn.tr("tray.started_body")
            )

    def show_normal(self) -> None:
        self.show()
        if self.cap is None and not service_running():
            self.open_camera()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_normal()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.tray_available:
            self.hide()
            event.ignore()
        else:
            event.accept()


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WebcamCCTV.Desktop.0.3")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("WebcamCCTV")
    app.setApplicationDisplayName("WebcamCCTV")
    app.setWindowIcon(_icon("camera", THEMES["dark"].accent))
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(not QSystemTrayIcon.isSystemTrayAvailable())
    cfg = load()
    apply_app_theme(cfg.theme)
    if not cfg.first_run_complete and FirstRunDialog(cfg).exec() != QDialog.DialogCode.Accepted:
        return 0
    window = Window(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
