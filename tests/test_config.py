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
