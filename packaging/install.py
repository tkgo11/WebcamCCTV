"""Localized startup registration for the current operating system."""

from pathlib import Path
import argparse
import platform
import shutil
import subprocess
import sys
from webcamcctv.i18n import Translator


def main() -> None:
    bootstrap = argparse.ArgumentParser()
    bootstrap.add_argument("--remove", action="store_true")
    bootstrap.add_argument("--language", choices=("en", "ko"))
    args = bootstrap.parse_args()
    tr = Translator(args.language)
    system = platform.system()
    if system == "Linux":
        target = Path.home() / ".config/systemd/user/webcamcctv.service"
        if args.remove:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(Path(__file__).with_name("webcamcctv.service"), target)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        if not args.remove:
            subprocess.run(["systemctl", "--user", "enable", "--now", "webcamcctv"], check=True)
    elif system == "Windows":
        name = "WebcamCCTV"
        command = f'"{sys.executable}" -m webcamcctv.service'
        operation = (
            ["/Delete", "/TN", name, "/F"]
            if args.remove
            else ["/Create", "/TN", name, "/SC", "ONLOGON", "/TR", command, "/F"]
        )
        subprocess.run(["schtasks", *operation], check=True)
    elif system == "Darwin":
        label = "com.webcamcctv.service"
        target = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
        domain = f"gui/{__import__('os').getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(target)], check=False)
        if args.remove:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            command = str(Path(sys.executable).resolve())
            target.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.webcamcctv.service</string>
<key>ProgramArguments</key><array><string>COMMAND</string><string>-m</string><string>webcamcctv.service</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
</dict></plist>
""".replace("COMMAND", command), "utf-8")
            subprocess.run(["plutil", "-lint", str(target)], check=True)
            subprocess.run(["launchctl", "bootstrap", domain, str(target)], check=True)
    else:
        raise SystemExit(tr.tr("installer.unsupported", system=system))
    print(tr.tr("installer.removed" if args.remove else "installer.installed"))


if __name__ == "__main__":
    main()
