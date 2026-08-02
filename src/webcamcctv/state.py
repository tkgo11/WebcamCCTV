"""Filesystem-backed service lifecycle and control state."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psutil
from platformdirs import user_state_dir

STATE_DIR = Path(user_state_dir("WebcamCCTV"))
STATUS = STATE_DIR / "status.json"
STOP = STATE_DIR / "stop.request"
MANUAL_RECORD = STATE_DIR / "manual-record.request"
LOCK = STATE_DIR / "service.lock"


def lock_pid() -> int | None:
    try:
        value = int(LOCK.read_text("ascii"))
    except (OSError, ValueError):
        return None
    return value if value > 0 else None


def process_is_service(pid: int) -> bool:
    """Return whether *pid* is a live WebcamCCTV service process."""
    try:
        command = " ".join(psutil.Process(pid).cmdline()).casefold()
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError):
        # An access-denied result still proves that the PID exists. Preserve the lock.
        return True
    return "webcamcctv.service" in command or "webcamcctv-service" in command


def service_running() -> bool:
    pid = lock_pid()
    return pid is not None and process_is_service(pid)


def acquire_lock() -> bool:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        existing = lock_pid()
        if existing is not None and process_is_service(existing):
            return False
        try:
            if time.time() - LOCK.stat().st_mtime < 5:
                return False
        except OSError:
            return False
        LOCK.unlink(missing_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def release_lock() -> None:
    if lock_pid() == os.getpid():
        LOCK.unlink(missing_ok=True)


def clear_control_markers() -> None:
    STOP.unlink(missing_ok=True)
    MANUAL_RECORD.unlink(missing_ok=True)


def request_stop() -> bool:
    if not service_running():
        clear_control_markers()
        return False
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STOP.touch()
    return True


def request_manual_record(enabled: bool) -> bool:
    if not service_running():
        MANUAL_RECORD.unlink(missing_ok=True)
        return False
    if enabled:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        MANUAL_RECORD.touch()
    else:
        MANUAL_RECORD.unlink(missing_ok=True)
    return True


def read_status() -> dict[str, object]:
    try:
        value = json.loads(STATUS.read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    data = value if isinstance(value, dict) else {}
    running = service_running()
    data["running"] = running
    if not running:
        data.update(camera_connected=False, recording=False)
    return data


def wait_for_stopped(timeout: float = 15.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while service_running() and time.monotonic() < deadline:
        time.sleep(interval)
    return not service_running()
