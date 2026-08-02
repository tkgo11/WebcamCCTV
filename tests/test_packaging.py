import runpy
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "packaging" / "assets" / "app_icon.ico"


def test_windows_release_uses_a_multiresolution_icon():
    build_release = runpy.run_path(str(ROOT / "packaging" / "build_release.py"))
    icon_args = build_release["executable_icon_args"]

    assert icon_args("posix") == []
    assert icon_args("nt") == [f"--icon={ICON}"]

    reserved, image_type, count = struct.unpack("<HHH", ICON.read_bytes()[:6])
    assert (reserved, image_type) == (0, 1)
    assert count == 7
