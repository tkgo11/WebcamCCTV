"""Versioned configuration with validation and atomic persistence."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import os
import shutil
import tempfile
from platformdirs import user_config_dir, user_videos_dir
from .i18n import SUPPORTED_LOCALES, Translator, detect_locale

SCHEMA_VERSION = 1


@dataclass(slots=True)
class CameraConfig:
    device: int = 0
    name: str = "Camera 1"
    width: int = 1280
    height: int = 720
    fps: float = 20.0
    rotation: int = 0
    mirror: bool = False


@dataclass(slots=True)
class MotionConfig:
    enabled: bool = True
    sensitivity: float = 0.04
    minimum_area: int = 1800
    pre_event_seconds: float = 3.0
    post_event_seconds: float = 8.0
    cooldown_seconds: float = 2.0


@dataclass(slots=True)
class StorageConfig:
    directory: str = field(default_factory=lambda: str(Path(user_videos_dir()) / "WebcamCCTV"))
    segment_seconds: int = 300
    retention_days: int = 14
    maximum_gib: float = 50.0
    minimum_free_gib: float = 2.0


@dataclass(slots=True)
class AppConfig:
    schema_version: int = SCHEMA_VERSION
    mode: str = "motion"
    camera: CameraConfig = field(default_factory=CameraConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    watermark_timestamp: bool = True
    preview_fps: float = 5.0
    language: str = field(default_factory=detect_locale)
    notification_language: str = ""
    date_time_format: str = ""
    first_run_complete: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                Translator(raw.get("language", detect_locale())).tr(
                    "validation.schema", version=raw.get("schema_version")
                )
            )
        cfg = cls(
            camera=CameraConfig(**raw.get("camera", {})),
            motion=MotionConfig(**raw.get("motion", {})),
            storage=StorageConfig(**raw.get("storage", {})),
            **{
                k: raw[k]
                for k in (
                    "schema_version",
                    "mode",
                    "watermark_timestamp",
                    "preview_fps",
                    "language",
                    "notification_language",
                    "date_time_format",
                    "first_run_complete",
                )
                if k in raw
            },
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        tr = Translator(self.language)
        errors: list[str] = []
        if self.language not in SUPPORTED_LOCALES:
            errors.append(tr.tr("validation.language"))
        if self.notification_language and self.notification_language not in SUPPORTED_LOCALES:
            errors.append(tr.tr("validation.notification_language"))
        if self.mode not in {"continuous", "motion", "manual"}:
            errors.append(tr.tr("validation.mode"))
        if not 1 <= self.camera.fps <= 120:
            errors.append(tr.tr("validation.fps"))
        if self.camera.width < 160 or self.camera.height < 120:
            errors.append(tr.tr("validation.resolution"))
        if self.camera.rotation not in {0, 90, 180, 270}:
            errors.append(tr.tr("validation.rotation"))
        if not 0 < self.motion.sensitivity < 1:
            errors.append(tr.tr("validation.sensitivity"))
        if self.motion.minimum_area < 1:
            errors.append(tr.tr("validation.motion_area"))
        if self.storage.segment_seconds < 5:
            errors.append(tr.tr("validation.segment"))
        if self.storage.retention_days < 1 or self.storage.maximum_gib <= 0:
            errors.append(tr.tr("validation.retention"))
        p = Path(self.storage.directory).expanduser()
        if "\0" in str(p):
            errors.append(tr.tr("validation.storage_path"))
        if errors:
            raise ValueError("; ".join(errors))


def config_path() -> Path:
    return Path(
        os.environ.get("WEBCAMCCTV_CONFIG", Path(user_config_dir("WebcamCCTV")) / "config.json")
    )


def load(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        return AppConfig()
    try:
        return AppConfig.from_dict(json.loads(target.read_text("utf-8")))
    except Exception:
        backup = target.with_suffix(".json.bak")
        if backup.exists():
            return AppConfig.from_dict(json.loads(backup.read_text("utf-8")))
        raise


def save(cfg: AppConfig, path: Path | None = None) -> Path:
    cfg.validate()
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_suffix(".json.bak"))
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(asdict(cfg), stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target
