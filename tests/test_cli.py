import json
import sys

from webcamcctv import cli
from webcamcctv.config import AppConfig


def invoke(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["webcamcctv", *arguments])
    return cli.main()


def test_status_rejects_stale_service_state(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load", lambda: AppConfig())
    monkeypatch.setattr(cli, "read_status", lambda: {"running": False})
    assert invoke(monkeypatch, ["--json", "status"]) == 3
    assert json.loads(capsys.readouterr().out) == {"running": False}


def test_stop_when_idle_returns_not_running(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load", lambda: AppConfig())
    monkeypatch.setattr(cli, "request_stop", lambda: False)
    assert invoke(monkeypatch, ["stop"]) == 3
    assert "not running" in capsys.readouterr().out


def test_manual_record_commands_require_manual_mode(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load", lambda: AppConfig(mode="continuous"))
    assert invoke(monkeypatch, ["record-start"]) == 5
    assert "manual recording mode" in capsys.readouterr().out


def test_manual_record_request_reaches_running_service(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load", lambda: AppConfig(mode="manual"))
    requested = []
    monkeypatch.setattr(
        cli, "request_manual_record", lambda enabled: requested.append(enabled) or True
    )
    assert invoke(monkeypatch, ["record-start"]) == 0
    assert requested == [True]
    assert "started" in capsys.readouterr().out


def test_start_reports_existing_service(monkeypatch, capsys):
    monkeypatch.setattr(cli, "service_running", lambda: True)
    assert cli.start_service(cli.Translator("en"), False) == 3
    assert "already running" in capsys.readouterr().out


def test_start_reports_early_process_failure(monkeypatch, capsys):
    class FailedProcess:
        def poll(self):
            return 1

    monkeypatch.setattr(cli, "service_running", lambda: False)
    monkeypatch.setattr(cli, "clear_control_markers", lambda: None)
    monkeypatch.setattr(cli, "companion_command", lambda *_: ["service"])
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *_args, **_kwargs: FailedProcess())
    assert cli.start_service(cli.Translator("en"), False) == 5
    assert "exited" in capsys.readouterr().out


def test_validate_config_returns_machine_readable_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load", lambda: (_ for _ in ()).throw(ValueError("bad config")))
    assert invoke(monkeypatch, ["--json", "validate-config"]) == 2
    assert json.loads(capsys.readouterr().out) == {"valid": False, "error": "bad config"}
