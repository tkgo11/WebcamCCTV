import json

import pytest

from webcamcctv.config import AppConfig, load, save


def test_atomic_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    cfg = AppConfig()
    cfg.camera.name = "Garage"
    save(cfg, p)
    assert load(p).camera.name == "Garage" and json.loads(p.read_text())["schema_version"] == 2


def test_v1_configuration_is_migrated(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"schema_version": 1, "camera": {"name": "Legacy"}}')
    assert load(p).camera.name == "Legacy"


def test_invalid_config_rejected():
    cfg = AppConfig()
    cfg.camera.fps = 0
    with pytest.raises(ValueError, match="frame rate"):
        cfg.validate()


def test_backup_restores_corruption(tmp_path):
    p = tmp_path / "config.json"
    save(AppConfig(), p)
    changed = AppConfig()
    changed.mode = "continuous"
    save(changed, p)
    p.write_text("broken")
    assert load(p).mode == "motion"


def test_invalid_primary_never_overwrites_last_valid_backup(tmp_path):
    path = tmp_path / "config.json"
    save(AppConfig(mode="motion"), path)
    save(AppConfig(mode="continuous"), path)
    path.write_text("broken", encoding="utf-8")
    save(AppConfig(mode="manual"), path)
    path.write_text("broken again", encoding="utf-8")
    assert load(path).mode == "motion"


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda config: setattr(config.motion, "post_event_seconds", -1), "cannot be negative"),
        (lambda config: setattr(config.storage, "minimum_free_gib", -1), "positive"),
        (lambda config: setattr(config.camera, "device", -1), "non-negative"),
        (lambda config: setattr(config, "preview_fps", 0), "between 1 and 60"),
        (lambda config: setattr(config.audio, "enabled", True), "not implemented"),
        (lambda config: setattr(config.features, "remote_api", True), "not implemented"),
    ],
)
def test_extended_validation_rejects_silent_noops(mutate, message):
    config = AppConfig()
    mutate(config)
    with pytest.raises(ValueError, match=message):
        config.validate()


def test_invalid_normalized_polygon_rejected():
    config = AppConfig()
    config.camera.privacy_masks = [[[0, 0], [1.2, 0], [0, 1]]]
    with pytest.raises(ValueError, match="polygons"):
        config.validate()
