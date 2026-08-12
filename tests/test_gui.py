"""Headless GUI smoke test when the platform Qt libraries are available."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

QApplication = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError).QApplication

from webcamcctv import gui
from webcamcctv.config import AppConfig


class FakeCapture:
    def __init__(self, _device):
        self.opened = True

    def isOpened(self):
        return self.opened

    def read(self):
        return True, np.zeros((24, 32, 3), dtype=np.uint8)

    def release(self):
        self.opened = False


def test_window_preview_manual_controls_and_service_handoff(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        gui,
        "discover",
        lambda **_kwargs: [{"index": 0, "name": "Camera 0", "width": 32, "height": 24}],
    )
    monkeypatch.setattr(gui, "service_running", lambda: False)
    status_data = {"running": False, "camera_connected": False, "recording": False}
    monkeypatch.setattr(gui, "read_status", lambda: status_data.copy())
    monkeypatch.setattr(gui.cv2, "VideoCapture", FakeCapture)
    launched = []
    monkeypatch.setattr(gui, "companion_command", lambda *_args: ["webcamcctv"])
    monkeypatch.setattr(
        gui.subprocess, "Popen", lambda command, **options: launched.append((command, options))
    )

    config = AppConfig(first_run_complete=True)
    config.storage.directory = str(tmp_path)
    window = gui.Window(config)
    window.tray_available = False
    assert window.theme.currentData() == "system"
    assert window.service_card.property("card") is True
    assert window.search.accessibleName()
    window.tick()
    assert window.cap is not None and window.preview.pixmap() is not None

    window.mode.setCurrentIndex(window.mode.findData("manual"))
    config.mode = "manual"
    status_data.update(running=True, mode="manual", recording=False)
    window.service_data = status_data.copy()
    window.update_controls()
    manual_buttons = {
        command: button
        for button, command in window.control_buttons
        if command.startswith("record-")
    }
    assert manual_buttons["record-start"].isEnabled()
    assert not manual_buttons["record-stop"].isEnabled()

    manual_requests = []
    monkeypatch.setattr(
        gui,
        "request_manual_record",
        lambda enabled: manual_requests.append(enabled) or True,
    )
    window.command("record-start")
    assert manual_requests == [True]
    assert not manual_buttons["record-start"].isEnabled()
    assert manual_buttons["record-stop"].isEnabled()

    window.command("start")
    assert window.cap is None
    assert launched[0][0][-3:] == ["--language", config.language, "start"]
    window.show_normal()
    assert window.cap is not None
    window.close()
    app.processEvents()


def test_window_marks_preview_unavailable_without_discovered_camera(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui, "discover", lambda **_kwargs: [])
    monkeypatch.setattr(gui, "service_running", lambda: False)
    monkeypatch.setattr(
        gui,
        "read_status",
        lambda: {"running": False, "camera_connected": False, "recording": False},
    )

    config = AppConfig(first_run_complete=True)
    config.storage.directory = str(tmp_path)
    window = gui.Window(config)
    window.tray_available = False

    assert window.cap is None
    assert window.preview_state.property("state") == "warning"
    assert window.preview_state.text() == "unavailable"
    assert window.preview.text() == "Camera is unavailable or being used by another application."

    window.close()
    app.processEvents()
