import plistlib
import sys

from webcamcctv import startup
from webcamcctv.startup import launch_agent, systemd_unit


def test_systemd_unit_quotes_source_environment_command():
    unit = systemd_unit(["/path with spaces/python", "-m", "webcamcctv.service", "100%"])
    assert 'ExecStart="/path with spaces/python" "-m" "webcamcctv.service" "100%%"' in unit
    assert "Restart=on-failure" in unit


def test_launch_agent_preserves_special_characters_in_paths():
    command = ["/Applications/Cameras & Tools/WebcamCCTV-Service", "--flag"]
    value = plistlib.loads(launch_agent(command))
    assert value["ProgramArguments"] == command
    assert value["KeepAlive"] == {"SuccessfulExit": False}


def test_windows_installer_uses_argument_safe_task_command(monkeypatch):
    calls = []
    monkeypatch.setattr(
        startup.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs))
    )
    startup.install_windows(["C:\\Program Files\\WebcamCCTV-Service.exe", "--flag"], False)
    command, options = calls[0]
    assert command[:3] == ["schtasks", "/Create", "/TN"]
    assert '"C:\\Program Files\\WebcamCCTV-Service.exe" --flag' in command
    assert options == {"check": True}


def test_linux_installer_generates_actual_runtime_command(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(startup.Path, "home", classmethod(lambda _class: tmp_path))
    monkeypatch.setattr(startup.subprocess, "run", lambda command, **kwargs: calls.append(command))
    startup.install_linux(["/venv/bin/python", "-m", "webcamcctv.service"], False)
    unit = (tmp_path / ".config/systemd/user/webcamcctv.service").read_text("utf-8")
    assert 'ExecStart="/venv/bin/python" "-m" "webcamcctv.service"' in unit
    assert calls[-1] == ["systemctl", "--user", "enable", "--now", "webcamcctv.service"]


def test_removal_does_not_require_adjacent_service_executable(monkeypatch, capsys):
    removed = []
    monkeypatch.setattr(sys, "argv", ["webcamcctv-startup", "--remove", "--language", "en"])
    monkeypatch.setattr(startup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        startup,
        "companion_command",
        lambda *_args: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )
    monkeypatch.setattr(
        startup, "install_linux", lambda command, remove: removed.append((command, remove))
    )
    assert startup.main() == 0
    assert removed == [([], True)]
    assert "removed" in capsys.readouterr().out
