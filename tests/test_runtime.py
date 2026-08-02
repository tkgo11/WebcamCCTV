from pathlib import Path

from webcamcctv import runtime


def test_companion_command_uses_module_when_not_frozen(monkeypatch) -> None:
    monkeypatch.delattr(runtime.sys, "frozen", raising=False)
    monkeypatch.setattr(runtime.sys, "executable", "/python")
    assert runtime.companion_command("WebcamCCTV-Service", "webcamcctv.service") == [
        "/python",
        "-m",
        "webcamcctv.service",
    ]


def test_companion_command_finds_frozen_sibling(monkeypatch, tmp_path: Path) -> None:
    suffix = ".exe" if runtime.os.name == "nt" else ""
    gui = tmp_path / f"WebcamCCTV-GUI{suffix}"
    service = tmp_path / f"WebcamCCTV-Service{suffix}"
    gui.touch()
    service.touch()
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.sys, "executable", str(gui))
    assert runtime.companion_command("WebcamCCTV-Service", "webcamcctv.service") == [
        str(service)
    ]
