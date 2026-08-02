"""Versioned configuration with validation and atomic persistence."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_videos_dir

from .i18n import SUPPORTED_LOCALES, Translator, detect_locale

SCHEMA_VERSION = 2


@dataclass(slots=True)
class CameraConfig:
    id: str = "camera-1"
    device: int = 0
    name: str = "Camera 1"
    width: int = 1280
    height: int = 720
    fps: float = 20.0
    rotation: int = 0
    mirror: bool = False
    enabled: bool = True
    controls: dict[str, float] = field(default_factory=dict)
    motion_zones: list[list[list[float]]] = field(default_factory=list)
    privacy_masks: list[list[list[float]]] = field(default_factory=list)


@dataclass(slots=True)
class AudioConfig:
    enabled: bool = False
    device: str = ""
    sample_rate: int = 48000
    channels: int = 1


@dataclass(slots=True)
class ScheduleConfig:
    enabled: bool = False
    weekdays: list[int] = field(default_factory=lambda: list(range(7)))
    start: str = "00:00"
    end: str = "23:59"
    record_when_locked: bool = False


@dataclass(slots=True)
class FeatureConfig:
    thumbnails: bool = True
    notifications: bool = False
    ai_model: str = ""
    remote_api: bool = False
    remote_bind: str = "127.0.0.1"
    encryption: bool = False
    sync_directory: str = ""
    encoder: str = "mp4v"


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
    cameras: list[CameraConfig] = field(default_factory=list)
    audio: AudioConfig = field(default_factory=AudioConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    watermark_timestamp: bool = True
    preview_fps: float = 5.0
    language: str = field(default_factory=detect_locale)
    notification_language: str = ""
    date_time_format: str = ""
    first_run_complete: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppConfig:
        if not isinstance(raw, dict):
            raise TypeError("configuration root must be an object")
        version = raw.get("schema_version", 1)
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version
            not in {
                1,
                SCHEMA_VERSION,
            }
        ):
            raise ValueError(
                Translator(
                    raw.get("language") if isinstance(raw.get("language"), str) else None
                ).tr("validation.schema", version=raw.get("schema_version"))
            )
        cameras = raw.get("cameras", [])
        if not isinstance(cameras, list):
            raise TypeError("cameras must be a list")
        cfg = cls(
            schema_version=SCHEMA_VERSION,
            camera=CameraConfig(**raw.get("camera", {})),
            cameras=[CameraConfig(**item) for item in cameras],
            audio=AudioConfig(**raw.get("audio", {})),
            schedule=ScheduleConfig(**raw.get("schedule", {})),
            features=FeatureConfig(**raw.get("features", {})),
            motion=MotionConfig(**raw.get("motion", {})),
            storage=StorageConfig(**raw.get("storage", {})),
            **{
                k: raw[k]
                for k in (
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
        language = self.language if isinstance(self.language, str) else None
        tr = Translator(language)
        errors: list[str] = []
        if self.language not in SUPPORTED_LOCALES:
            errors.append(tr.tr("validation.language"))
        if self.notification_language and self.notification_language not in SUPPORTED_LOCALES:
            errors.append(tr.tr("validation.notification_language"))
        if not isinstance(self.notification_language, str):
            errors.append(tr.tr("validation.notification_language"))
        if not isinstance(self.date_time_format, str):
            errors.append(tr.tr("validation.date_time_format"))
        if not isinstance(self.mode, str) or self.mode not in {"continuous", "motion", "manual"}:
            errors.append(tr.tr("validation.mode"))
        if (
            not isinstance(self.camera.device, int)
            or isinstance(self.camera.device, bool)
            or self.camera.device < 0
        ):
            errors.append(tr.tr("validation.camera_device"))
        if (
            not isinstance(self.camera.id, str)
            or not self.camera.id.strip()
            or len(self.camera.id) > 64
        ):
            errors.append(tr.tr("validation.camera_id"))
        if (
            not isinstance(self.camera.name, str)
            or not self.camera.name.strip()
            or len(self.camera.name) > 120
        ):
            errors.append(tr.tr("validation.camera_name"))
        if (
            not isinstance(self.camera.fps, (int, float))
            or isinstance(self.camera.fps, bool)
            or not 1 <= self.camera.fps <= 120
        ):
            errors.append(tr.tr("validation.fps"))
        if (
            not isinstance(self.camera.width, int)
            or isinstance(self.camera.width, bool)
            or not isinstance(self.camera.height, int)
            or isinstance(self.camera.height, bool)
            or self.camera.width < 160
            or self.camera.height < 120
        ):
            errors.append(tr.tr("validation.resolution"))
        if (
            not isinstance(self.camera.rotation, int)
            or isinstance(self.camera.rotation, bool)
            or self.camera.rotation not in {0, 90, 180, 270}
        ):
            errors.append(tr.tr("validation.rotation"))
        if self.cameras:
            errors.append(tr.tr("validation.multiple_cameras"))
        boolean_values = (
            self.camera.mirror,
            self.camera.enabled,
            self.audio.enabled,
            self.schedule.enabled,
            self.schedule.record_when_locked,
            self.features.thumbnails,
            self.features.notifications,
            self.features.remote_api,
            self.features.encryption,
            self.motion.enabled,
            self.watermark_timestamp,
            self.first_run_complete,
        )
        if any(not isinstance(value, bool) for value in boolean_values):
            errors.append(tr.tr("validation.boolean"))
        if self.camera.enabled is False:
            errors.append(tr.tr("validation.camera_disabled"))
        if self.mode == "motion" and self.motion.enabled is False:
            errors.append(tr.tr("validation.motion_disabled"))
        if not _valid_polygons(self.camera.motion_zones) or not _valid_polygons(
            self.camera.privacy_masks
        ):
            errors.append(tr.tr("validation.polygons"))
        if not isinstance(self.camera.controls, dict) or any(
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            for name, value in self.camera.controls.items()
        ):
            errors.append(tr.tr("validation.camera_controls"))
        if self.audio.enabled:
            errors.append(tr.tr("validation.audio_unsupported"))
        if (
            not isinstance(self.audio.sample_rate, int)
            or isinstance(self.audio.sample_rate, bool)
            or self.audio.sample_rate not in {8000, 16000, 22050, 44100, 48000, 96000}
        ):
            errors.append(tr.tr("validation.audio_rate"))
        if (
            not isinstance(self.audio.channels, int)
            or isinstance(self.audio.channels, bool)
            or self.audio.channels not in {1, 2}
        ):
            errors.append(tr.tr("validation.audio_channels"))
        if not _valid_weekdays(self.schedule.weekdays):
            errors.append(tr.tr("validation.schedule_weekdays"))
        for value in (self.schedule.start, self.schedule.end):
            if (
                not isinstance(value, str)
                or re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is None
            ):
                errors.append(tr.tr("validation.schedule_time"))
                break
        if self.schedule.record_when_locked:
            errors.append(tr.tr("validation.lock_detection_unsupported"))
        if not isinstance(self.features.remote_bind, str) or (
            self.features.remote_api and self.features.remote_bind != "127.0.0.1"
        ):
            errors.append(tr.tr("validation.remote_loopback"))
        if self.features.remote_api:
            errors.append(tr.tr("validation.remote_unsupported"))
        if self.features.notifications:
            errors.append(tr.tr("validation.notifications_unsupported"))
        if self.features.encryption:
            errors.append(tr.tr("validation.encryption_unsupported"))
        if self.features.ai_model:
            errors.append(tr.tr("validation.ai_unsupported"))
        if not isinstance(self.features.encoder, str) or self.features.encoder not in {
            "mp4v",
            "avc1",
            "MJPG",
        }:
            errors.append(tr.tr("validation.encoder"))
        if (
            not isinstance(self.motion.sensitivity, (int, float))
            or isinstance(self.motion.sensitivity, bool)
            or not 0 < self.motion.sensitivity < 1
        ):
            errors.append(tr.tr("validation.sensitivity"))
        if (
            not isinstance(self.motion.minimum_area, int)
            or isinstance(self.motion.minimum_area, bool)
            or self.motion.minimum_area < 1
        ):
            errors.append(tr.tr("validation.motion_area"))
        for timing in (
            self.motion.pre_event_seconds,
            self.motion.post_event_seconds,
            self.motion.cooldown_seconds,
        ):
            if not isinstance(timing, (int, float)) or isinstance(timing, bool) or timing < 0:
                errors.append(tr.tr("validation.motion_timing"))
                break
        if (
            not isinstance(self.storage.segment_seconds, int)
            or isinstance(self.storage.segment_seconds, bool)
            or self.storage.segment_seconds < 5
        ):
            errors.append(tr.tr("validation.segment"))
        if (
            not isinstance(self.storage.retention_days, int)
            or isinstance(self.storage.retention_days, bool)
            or self.storage.retention_days < 1
            or not isinstance(self.storage.maximum_gib, (int, float))
            or isinstance(self.storage.maximum_gib, bool)
            or self.storage.maximum_gib <= 0
            or not isinstance(self.storage.minimum_free_gib, (int, float))
            or isinstance(self.storage.minimum_free_gib, bool)
            or self.storage.minimum_free_gib < 0
        ):
            errors.append(tr.tr("validation.retention"))
        if not isinstance(self.storage.directory, str) or not self.storage.directory.strip():
            errors.append(tr.tr("validation.storage_path"))
        else:
            p = Path(self.storage.directory).expanduser()
            if "\0" in str(p):
                errors.append(tr.tr("validation.storage_path"))
            if not isinstance(self.features.sync_directory, str):
                errors.append(tr.tr("validation.sync_path"))
                sync = None
            elif self.features.sync_directory:
                sync = Path(self.features.sync_directory).expanduser()
            else:
                sync = None
            if sync is not None:
                try:
                    if sync.resolve() == p.resolve() or p.resolve() in sync.resolve().parents:
                        errors.append(tr.tr("validation.sync_path"))
                except OSError:
                    errors.append(tr.tr("validation.sync_path"))
        if (
            not isinstance(self.preview_fps, (int, float))
            or isinstance(self.preview_fps, bool)
            or not 1 <= self.preview_fps <= 60
        ):
            errors.append(tr.tr("validation.preview_fps"))
        if errors:
            raise ValueError("; ".join(errors))


def _valid_polygons(polygons: object) -> bool:
    if not isinstance(polygons, list):
        return False
    for polygon in polygons:
        if not isinstance(polygon, list) or len(polygon) < 3:
            return False
        for point in polygon:
            if not isinstance(point, list) or len(point) != 2:
                return False
            if any(
                not isinstance(coordinate, (int, float))
                or isinstance(coordinate, bool)
                or not 0 <= coordinate <= 1
                for coordinate in point
            ):
                return False
    return True


def _valid_weekdays(weekdays: object) -> bool:
    if not isinstance(weekdays, list):
        return False
    if any(
        not isinstance(day, int) or isinstance(day, bool) or day not in range(7) for day in weekdays
    ):
        return False
    return len(set(weekdays)) == len(weekdays)


def config_path() -> Path:
    return Path(
        os.environ.get("WEBCAMCCTV_CONFIG", Path(user_config_dir("WebcamCCTV")) / "config.json")
    )


def _backup_path(target: Path) -> Path:
    return (
        target.with_suffix(target.suffix + ".bak")
        if target.suffix
        else target.with_name(target.name + ".bak")
    )


def load(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        return AppConfig()
    try:
        return AppConfig.from_dict(json.loads(target.read_text("utf-8")))
    except (OSError, ValueError, TypeError):
        backup = _backup_path(target)
        if backup.exists():
            return AppConfig.from_dict(json.loads(backup.read_text("utf-8")))
        raise


def save(cfg: AppConfig, path: Path | None = None) -> Path:
    cfg.validate()
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            AppConfig.from_dict(json.loads(target.read_text("utf-8")))
        except (OSError, ValueError, TypeError):
            pass
        else:
            backup = _backup_path(target)
            backup_tmp = backup.with_suffix(backup.suffix + ".tmp")
            shutil.copy2(target, backup_tmp)
            os.replace(backup_tmp, backup)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(asdict(cfg), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY)
        except OSError:
            pass
        else:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return target
