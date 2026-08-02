from datetime import datetime

from webcamcctv.config import AppConfig, ScheduleConfig
from webcamcctv.features import Notification, Notifier, redact, schedule_active, write_diagnostics


def test_overnight_schedule():
    schedule = ScheduleConfig(enabled=True, start="22:00", end="06:00")
    assert schedule_active(schedule, datetime(2026, 8, 3, 23, 0))
    assert not schedule_active(schedule, datetime(2026, 8, 3, 12, 0))


def test_notification_deduplicates():
    delivered = []
    notifier = Notifier(delivered.append)
    event = Notification("motion", "detected")
    assert notifier.send(event, 10)
    assert not notifier.send(event, 20)
    assert notifier.send(event, 41)
    assert delivered == [event, event]


def test_diagnostics_redacts_secrets(tmp_path):
    assert redact({"api_token": "canary", "normal": "ok"}) == {
        "api_token": "<redacted>", "normal": "ok"
    }
    target = write_diagnostics(tmp_path / "diagnostics.json", AppConfig(), {"token": "canary"})
    assert "canary" not in target.read_text("utf-8")
