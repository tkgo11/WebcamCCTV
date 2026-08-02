import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from webcamcctv.config import AppConfig, load, save
from webcamcctv.i18n import (
    SUPPORTED_LOCALES,
    Translator,
    detect_locale,
    format_datetime,
    format_duration,
    format_size,
    placeholders,
)
from webcamcctv.storage import StorageManager


@pytest.mark.parametrize("language", SUPPORTED_LOCALES)
def test_every_locale_loads_and_has_matching_keys_and_placeholders(language):
    root = Path("src/webcamcctv/locales")
    english = json.loads((root / "en.json").read_text("utf-8"))
    selected = json.loads((root / f"{language}.json").read_text("utf-8"))
    assert selected.keys() == english.keys()
    assert all(placeholders(selected[key]) == placeholders(value) for key, value in english.items())
    assert Translator(language).tr("settings.camera") not in {"", "settings.camera"}


def test_korean_os_locale_detection(monkeypatch):
    for name in ("WEBCAMCCTV_LOCALE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    assert detect_locale() == "ko"


def test_locale_formatting():
    value = datetime(2026, 8, 2, 13, 5, 9, tzinfo=timezone.utc)
    assert "오후" in format_datetime(value, "ko") and "PM" in format_datetime(value, "en")
    assert format_duration(60, "ko") == "1분" and format_duration(1, "en") == "1 second"
    assert "GiB" in format_size(2 * 1024**3, "ko")


def test_korean_configuration_path_and_metadata_roundtrip(tmp_path):
    root = tmp_path / "감시 영상"
    config_path = tmp_path / "사용자 설정.json"
    cfg = AppConfig(language="ko")
    cfg.camera.name = "현관 카메라"
    cfg.storage.directory = str(root)
    save(cfg, config_path)
    restored = load(config_path)
    assert restored.camera.name == "현관 카메라" and restored.storage.directory == str(root)
    storage = StorageManager(root, 1, 7, 0)
    video = storage.recording_path("현관 카메라", 1)
    video.touch()
    storage.write_metadata(video, {"camera": "현관 카메라", "event": "움직임 감지"})
    assert "현관 카메라" in video.name
    assert json.loads(video.with_suffix(".json").read_text("utf-8"))["event"] == "움직임 감지"


def test_fallback_and_pseudo_localization(monkeypatch, caplog):
    tr = Translator("ko", development=True)
    tr.messages.pop("settings.camera")
    assert tr.tr("settings.camera") == "Camera"
    assert tr.tr("missing.key") == "⟦missing.key⟧"
    monkeypatch.setenv("WEBCAMCCTV_PSEUDO", "1")
    assert Translator("en").tr("settings.save").startswith("⟦")
