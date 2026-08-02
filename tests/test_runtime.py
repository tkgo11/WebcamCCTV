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
    gui = tmp_path / "WebcamCCTV-GUI"
    service = tmp_path / "WebcamCCTV-Service"
    gui.touch()
    service.touch()
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.sys, "executable", str(gui))
    monkeypatch.setattr(runtime.os, "name", "posix")
    assert runtime.companion_command("WebcamCCTV-Service", "webcamcctv.service") == [
        str(service)
    ]
