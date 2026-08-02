import json
import os

from webcamcctv import state


def use_temporary_state(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "STATE_DIR", tmp_path)
    monkeypatch.setattr(state, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(state, "STOP", tmp_path / "stop.request")
    monkeypatch.setattr(state, "MANUAL_RECORD", tmp_path / "manual-record.request")
    monkeypatch.setattr(state, "LOCK", tmp_path / "service.lock")


def test_stale_status_is_never_reported_as_running(monkeypatch, tmp_path):
    use_temporary_state(monkeypatch, tmp_path)
    state.STATUS.write_text(json.dumps({"running": True, "recording": True}), encoding="utf-8")
    assert state.read_status() == {
        "running": False,
        "recording": False,
        "camera_connected": False,
    }


def test_idle_stop_clears_poisoned_control_markers(monkeypatch, tmp_path):
    use_temporary_state(monkeypatch, tmp_path)
    state.STOP.touch()
    state.MANUAL_RECORD.touch()
    assert state.request_stop() is False
    assert not state.STOP.exists() and not state.MANUAL_RECORD.exists()


def test_live_service_accepts_stop_and_manual_requests(monkeypatch, tmp_path):
    use_temporary_state(monkeypatch, tmp_path)
    state.LOCK.write_text(str(os.getpid()), encoding="ascii")
    monkeypatch.setattr(state, "process_is_service", lambda _pid: True)
    assert state.request_manual_record(True)
    assert state.MANUAL_RECORD.exists()
    assert state.request_stop()
    assert state.STOP.exists()


def test_lock_release_only_removes_current_process_lock(monkeypatch, tmp_path):
    use_temporary_state(monkeypatch, tmp_path)
    assert state.acquire_lock()
    state.release_lock()
    assert not state.LOCK.exists()


def test_fresh_incomplete_lock_is_treated_as_startup_race(monkeypatch, tmp_path):
    use_temporary_state(monkeypatch, tmp_path)
    state.LOCK.touch()
    assert state.acquire_lock() is False
