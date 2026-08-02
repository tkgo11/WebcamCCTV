"""Localized UTF-8 administrative command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import cv2

from . import __version__
from .cameras import discover
from .config import config_path, load
from .i18n import Translator
from .runtime import companion_command
from .state import (
    STATE_DIR,
    clear_control_markers,
    read_status,
    request_manual_record,
    request_stop,
    service_running,
    wait_for_stopped,
)

COMMANDS = [
    "start",
    "stop",
    "restart",
    "status",
    "validate-config",
    "list-cameras",
    "test-camera",
    "snapshot",
    "show-log-path",
    "version",
    "diagnostics",
    "record-start",
    "record-stop",
]


def emit(value: object, machine: bool) -> None:
    if machine or not isinstance(value, str):
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print(value)


def parser(tr: Translator) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="webcamcctv", description=tr.tr("cli.description"))
    result.add_argument("--json", action="store_true", help=tr.tr("cli.json_help"))
    result.add_argument("--language", choices=("en", "ko"), help=tr.tr("language.label"))
    result.add_argument("command", choices=COMMANDS, help=tr.tr("cli.command_help"))
    result.add_argument("--output", type=Path)
    return result


def start_service(tr: Translator, machine: bool) -> int:
    if service_running():
        emit(tr.tr("service.already_running"), machine)
        return 3
    clear_control_markers()
    flags = 0x08000000 if os.name == "nt" else 0
    process = subprocess.Popen(
        companion_command("WebcamCCTV-Service", "webcamcctv.service"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        creationflags=flags,
    )
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if service_running():
            emit(tr.tr("service.started"), machine)
            return 0
        if process.poll() is not None:
            emit(tr.tr("service.start_failed"), machine)
            return 5
        time.sleep(0.05)
    emit(tr.tr("service.started"), machine)
    return 0


def main() -> int:
    # Pre-parse language without preventing the normal parser from reporting errors.
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--language", choices=("en", "ko"))
    selected, _ = bootstrap.parse_known_args()
    try:
        configured = load().language
    except (OSError, ValueError, TypeError):
        configured = None
    tr = Translator(selected.language or configured)
    args = parser(tr).parse_args()
    machine = args.json
    if args.command == "version":
        emit({"version": __version__} if machine else __version__, machine)
        return 0
    if args.command == "validate-config":
        try:
            cfg = load()
            cfg.validate()
            data = {"valid": True, "path": str(config_path())}
            emit(data if machine else tr.tr("cli.config_valid", path=config_path()), machine)
            return 0
        except (OSError, ValueError, TypeError) as exc:
            emit({"valid": False, "error": str(exc)}, True)
            return 2
    if args.command == "list-cameras":
        emit(discover(language=tr.language), machine)
        return 0
    if args.command == "status":
        data = read_status()
        emit(data, machine)
        return 0 if data.get("running") else 3
    if args.command == "stop":
        requested = request_stop()
        emit(tr.tr("service.stop_requested" if requested else "service.not_running"), machine)
        return 0 if requested else 3
    if args.command == "restart" and service_running():
        request_stop()
        if not wait_for_stopped():
            emit(tr.tr("service.stop_timeout"), machine)
            return 5
    if args.command in {"start", "restart"}:
        return start_service(tr, machine)
    if args.command in {"record-start", "record-stop"}:
        cfg = load()
        if cfg.mode != "manual":
            emit(tr.tr("recording.manual_mode_required"), machine)
            return 5
        requested = request_manual_record(args.command == "record-start")
        key = (
            "recording.manual_started"
            if args.command == "record-start"
            else "recording.manual_stopped"
        )
        emit(tr.tr(key if requested else "service.not_running"), machine)
        return 0 if requested else 3
    cfg = load()
    cameras = discover(cfg.camera.device + 1, tr.language)
    if args.command == "test-camera":
        available = any(camera["index"] == cfg.camera.device for camera in cameras)
        emit(
            {"available": available}
            if machine
            else tr.tr("cli.camera_available" if available else "cli.camera_unavailable"),
            machine,
        )
        return 0 if available else 4
    if args.command == "snapshot":
        cap = cv2.VideoCapture(cfg.camera.device)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            emit({"error": tr.tr("cli.camera_unavailable")}, True)
            return 4
        from .service import Service

        service = Service(cfg)
        frame = service.transform(frame)
        target = args.output or service.storage.snapshot_path(cfg.camera.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), frame):
            emit({"error": "snapshot could not be written"}, True)
            return 2
        emit({"path": str(target)} if machine else str(target), machine)
        return 0
    if args.command == "diagnostics":
        from .features import write_diagnostics

        target = args.output or STATE_DIR / "diagnostics.json"
        write_diagnostics(target, cfg, read_status())
        emit({"path": str(target)} if machine else str(target), machine)
        return 0
    if args.command == "show-log-path":
        emit(str(STATE_DIR) if machine else tr.tr("cli.log_path", path=STATE_DIR), machine)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
