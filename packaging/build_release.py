"""Build a native, self-contained WebcamCCTV release archive."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WORK = ROOT / "build" / "pyinstaller"


def run_pyinstaller(name: str, launcher: str, *, windowed: bool = False) -> None:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        f"--name={name}",
        f"--paths={ROOT / 'src'}",
        "--collect-data=webcamcctv",
        f"--distpath={DIST}",
        f"--workpath={WORK / name}",
        f"--specpath={WORK / 'spec'}",
    ]
    if windowed:
        command.append("--windowed")
    command.append(str(ROOT / "packaging" / launcher))
    subprocess.run(command, cwd=ROOT, check=True)


def copy_product_files(stage: Path) -> None:
    suffix = ".exe" if os.name == "nt" else ""
    for name in ("WebcamCCTV-CLI", "WebcamCCTV-Service"):
        shutil.copy2(DIST / f"{name}{suffix}", stage / f"{name}{suffix}")

    mac_app = DIST / "WebcamCCTV-GUI.app"
    if mac_app.exists():
        shutil.copytree(mac_app, stage / mac_app.name)
    else:
        shutil.copy2(DIST / f"WebcamCCTV-GUI{suffix}", stage / f"WebcamCCTV-GUI{suffix}")

    for relative in ("README.md", "LICENSE"):
        shutil.copy2(ROOT / relative, stage / relative)
    shutil.copytree(ROOT / "docs", stage / "docs")
    shutil.copytree(ROOT / "config", stage / "config")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def archive(stage: Path, destination: Path) -> None:
    if destination.suffix == ".zip":
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    bundle.write(path, Path(stage.name) / path.relative_to(stage))
    else:
        with tarfile.open(destination, "w:gz") as bundle:
            bundle.add(stage, arcname=stage.name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    args = parser.parse_args()

    shutil.rmtree(DIST, ignore_errors=True)
    shutil.rmtree(WORK, ignore_errors=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    run_pyinstaller("WebcamCCTV-GUI", "launch_gui.py", windowed=True)
    run_pyinstaller("WebcamCCTV-Service", "launch_service.py")
    run_pyinstaller("WebcamCCTV-CLI", "launch_cli.py")

    system = platform.system().lower()
    platform_name = {"darwin": "macos", "windows": "windows", "linux": "linux"}.get(system)
    if platform_name is None:
        raise SystemExit(f"Unsupported release platform: {platform.system()}")
    product = f"WebcamCCTV-{args.version}-{platform_name}"
    stage = args.output_dir / product
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    copy_product_files(stage)

    extension = ".zip" if system in {"windows", "darwin"} else ".tar.gz"
    destination = args.output_dir / f"{product}{extension}"
    archive(stage, destination)
    shutil.rmtree(stage)
    checksum = destination.with_name(destination.name + ".sha256")
    checksum.write_text(f"{sha256(destination)}  {destination.name}\n", encoding="ascii")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
