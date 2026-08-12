"""End-to-end simulation test for WebcamCCTV CLI, service state machine, and Qt GUI."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QApplication = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError).QApplication

from webcamcctv import cli, service, state
from webcamcctv.config import AppConfig, save


def test_e2e_service_lifecycle_and_cli_coordination(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])

    # Setup isolated state and recording directories
    state_dir = tmp_path / "state"
    storage_dir = tmp_path / "storage"
    monkeypatch.setattr(state, "STATE_DIR", state_dir)
    monkeypatch.setattr(state, "STATUS", state_dir / "status.json")
    monkeypatch.setattr(state, "STOP", state_dir / "stop.request")
    monkeypatch.setattr(state, "MANUAL_RECORD", state_dir / "manual-record.request")
    monkeypatch.setattr(state, "LOCK", state_dir / "service.lock")

    cfg = AppConfig(first_run_complete=True, mode="manual")
    cfg.storage.directory = str(storage_dir)
    config_path = tmp_path / "config.json"
    save(cfg, config_path)
    monkeypatch.setattr(cli, "config_path", lambda: config_path)
    monkeypatch.setattr(service, "load", lambda: cfg)

    # 1. Initially service is not running
    assert state.service_running() is False
    assert state.read_status() == {"running": False, "camera_connected": False, "recording": False}

    # 2. Start service simulation via Service instance loop with mock capture
    class MockCapture:
        def __init__(self, _device):
            self.opened = True

        def isOpened(self):
            return self.opened

        def set(self, _prop, _value):
            return True

        def read(self):
            import numpy as np

            return True, np.zeros((480, 640, 3), dtype=np.uint8)

        def release(self):
            self.opened = False

    monkeypatch.setattr(service.cv2, "VideoCapture", MockCapture)
    monkeypatch.setattr(service.cv2, "VideoWriter_fourcc", lambda *_: 0)

    class MockWriter:
        def __init__(self, *args, **kwargs):
            self.opened = True

        def isOpened(self):
            return True

        def write(self, frame):
            pass

        def release(self):
            self.opened = False

    monkeypatch.setattr(service.cv2, "VideoWriter", MockWriter)

    # Mock process_is_service so test process is recognized as the service
    monkeypatch.setattr(state, "process_is_service", lambda _pid: True)

    svc = service.Service(cfg)
    assert state.acquire_lock() is True
    assert svc.connect() is True
    svc.status(message_key="service.starting", message="starting")

    # Verify status reflects running state
    status = state.read_status()
    assert status["running"] is True

    # 3. Test manual recording markers via state helpers
    assert state.request_manual_record(True) is True
    assert state.MANUAL_RECORD.exists() is True

    # Run one iteration of service loop
    _, raw = svc.capture.read()
    frame = svc.transform(raw)
    svc.begin(frame, 0.5)
    assert svc.writer is not None

    # Stop manual recording
    assert state.request_manual_record(False) is True
    assert state.MANUAL_RECORD.exists() is False
    svc.finish()

    # 4. Stop service and release lock
    svc.stop.set()
    state.release_lock()
    assert state.service_running() is False

    app.processEvents()
