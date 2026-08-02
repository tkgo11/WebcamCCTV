"""Install or remove per-user login startup for the headless service."""

from __future__ import annotations

import argparse
import os
import platform
import plistlib
import subprocess
from pathlib import Path

from .i18n import Translator
from .runtime import companion_command

SERVICE_NAME = "webcamcctv.service"
LAUNCH_AGENT_LABEL = "com.webcamcctv.service"


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"') + '"'


def systemd_unit(command: list[str]) -> str:
    executable = " ".join(_systemd_quote(part) for part in command)
    return f"""[Unit]
Description=WebcamCCTV headless surveillance service
After=graphical-session.target

[Service]
Type=simple
ExecStart={executable}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
"""


def install_linux(command: list[str], remove: bool) -> None:
    target = Path.home() / ".config/systemd/user" / SERVICE_NAME
    if remove:
        subprocess.run(["systemctl", "--user", "disable", "--now", SERVICE_NAME], check=False)
        target.unlink(missing_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(systemd_unit(command), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    if not remove:
        subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], check=True)


def install_windows(command: list[str], remove: bool) -> None:
    name = "WebcamCCTV"
    if remove:
        subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"], check=False)
        return
    subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN",
            name,
            "/SC",
            "ONLOGON",
            "/TR",
            subprocess.list2cmdline(command),
            "/F",
        ],
        check=True,
    )


def launch_agent(command: list[str]) -> bytes:
    return plistlib.dumps(
        {
            "Label": LAUNCH_AGENT_LABEL,
            "ProgramArguments": command,
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
        },
        fmt=plistlib.FMT_XML,
        sort_keys=False,
    )


def install_macos(command: list[str], remove: bool) -> None:
    target = Path.home() / "Library/LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(target)], check=False)
    if remove:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(launch_agent(command))
    subprocess.run(["plutil", "-lint", str(target)], check=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--language", choices=("en", "ko"))
    args = parser.parse_args()
    translator = Translator(args.language)
    command = [] if args.remove else companion_command("WebcamCCTV-Service", "webcamcctv.service")
    system = platform.system()
    if system == "Linux":
        install_linux(command, args.remove)
    elif system == "Windows":
        install_windows(command, args.remove)
    elif system == "Darwin":
        install_macos(command, args.remove)
    else:
        raise SystemExit(translator.tr("installer.unsupported", system=system))
    print(translator.tr("installer.removed" if args.remove else "installer.installed"))
    return 0
