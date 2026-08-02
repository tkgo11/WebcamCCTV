"""Localized UTF-8 administrative command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time

from . import __version__
from .cameras import discover
from .config import config_path, load
from .i18n import Translator
from .runtime import companion_command
from .service import STATE_DIR, STATUS, STOP

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
    return result


def main() -> int:
    # Pre-parse language without preventing the normal parser from reporting errors.
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--language", choices=("en", "ko"))
    selected, _ = bootstrap.parse_known_args()
    try:
        configured = load().language
    except Exception:
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
        except Exception as exc:
            emit({"valid": False, "error": str(exc)}, True)
            return 2
    if args.command == "list-cameras":
        emit(discover(language=tr.language), machine)
        return 0
    if args.command == "status":
        data = json.loads(STATUS.read_text("utf-8")) if STATUS.exists() else {"running": False}
        emit(data, machine)
        return 0 if data.get("running") else 3
    if args.command == "stop":
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STOP.touch()
        emit(tr.tr("service.stop_requested"), machine)
        return 0
    if args.command == "restart":
        STOP.touch()
        time.sleep(2)
    if args.command in {"start", "restart"}:
        flags = 0x08000000 if os.name == "nt" else 0
        subprocess.Popen(
            companion_command("WebcamCCTV-Service", "webcamcctv.service"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            creationflags=flags,
        )
        emit(tr.tr("service.started"), machine)
        return 0
    cameras = discover(load().camera.device + 1, tr.language)
    if args.command == "test-camera":
        available = any(camera["index"] == load().camera.device for camera in cameras)
        emit(
            {"available": available}
            if machine
            else tr.tr("cli.camera_available" if available else "cli.camera_unavailable"),
            machine,
        )
        return 0 if available else 4
    if args.command == "snapshot":
        emit({"error": tr.tr("cli.snapshot_unsupported")}, True)
        return 5
    if args.command == "show-log-path":
        emit(str(STATE_DIR) if machine else tr.tr("cli.log_path", path=STATE_DIR), machine)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
