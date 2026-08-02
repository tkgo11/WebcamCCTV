from datetime import UTC, datetime

from webcamcctv.config import AppConfig, ScheduleConfig
from webcamcctv.features import Notification, Notifier, redact, schedule_active, write_diagnostics


def test_overnight_schedule():
    schedule = ScheduleConfig(enabled=True, start="22:00", end="06:00")
    assert schedule_active(schedule, datetime(2026, 8, 3, 23, 0, tzinfo=UTC))
    assert not schedule_active(schedule, datetime(2026, 8, 3, 12, 0, tzinfo=UTC))


def test_overnight_schedule_uses_previous_weekday_after_midnight():
    monday = ScheduleConfig(enabled=True, weekdays=[0], start="22:00", end="06:00")
    assert schedule_active(monday, datetime(2026, 8, 3, 23, 0, tzinfo=UTC))
    assert schedule_active(monday, datetime(2026, 8, 4, 2, 0, tzinfo=UTC))
    assert not schedule_active(monday, datetime(2026, 8, 5, 2, 0, tzinfo=UTC))


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
        "api_token": "<redacted>",
        "normal": "ok",
    }
    target = write_diagnostics(tmp_path / "diagnostics.json", AppConfig(), {"token": "canary"})
    assert "canary" not in target.read_text("utf-8")
    assert "Camera 1" not in target.read_text("utf-8")
