"""Headless capture service with reconnect, motion events and pre/post buffering."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from collections import deque
from pathlib import Path
from threading import Event
from typing import Any

import cv2
import numpy as np

from .config import AppConfig, load
from .features import schedule_active
from .i18n import Translator
from .motion import MotionDetector
from .state import (
    MANUAL_RECORD,
    STATE_DIR,
    STATUS,
    STOP,
    acquire_lock,
    clear_control_markers,
    release_lock,
)
from .storage import StorageManager, file_sha256

log = logging.getLogger("webcamcctv.service")


class Service:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.trn = Translator(cfg.language)
        self.stop = Event()
        s = cfg.storage
        self.storage = StorageManager(
            Path(s.directory).expanduser(), s.maximum_gib, s.retention_days, s.minimum_free_gib
        )
        self.detector = MotionDetector(cfg.motion.sensitivity, cfg.motion.minimum_area)
        self.capture: Any = None
        self.writer: Any = None
        self.path: Path | None = None
        self.working_path: Path | None = None
        self.thumbnail: np.ndarray | None = None
        self.storage.reconcile()
        self.storage.cleanup()
        self.started = 0.0
        self.last_motion = 0.0
        self.last_finished = float("-inf")
        self.last_status = 0.0
        self.buffer: deque[tuple[float, np.ndarray]] = deque(
            maxlen=max(0, int(cfg.camera.fps * cfg.motion.pre_event_seconds))
        )

    def status(self, **extra: object) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "pid": os.getpid(),
            "running": not self.stop.is_set(),
            "camera_connected": self.capture is not None and self.capture.isOpened(),
            "recording": self.writer is not None,
            "mode": self.cfg.mode,
            "updated": time.time(),
            **extra,
        }
        tmp = STATUS.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATUS)

    def connect(self) -> bool:
        cap = cv2.VideoCapture(self.cfg.camera.device)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.camera.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.camera.height)
        cap.set(cv2.CAP_PROP_FPS, self.cfg.camera.fps)
        for name, value in self.cfg.camera.controls.items():
            prop = getattr(cv2, f"CAP_PROP_{name.upper()}", None)
            if prop is not None:
                cap.set(prop, value)
        if not cap.isOpened():
            cap.release()
            self.capture = None
            return False
        self.capture = cap
        self.detector.reset()
        self.buffer.clear()
        return True

    def transform(self, frame: np.ndarray) -> np.ndarray:
        if self.cfg.camera.mirror:
            frame = cv2.flip(frame, 1)
        if self.cfg.camera.rotation:
            frame = cv2.rotate(
                frame,
                {
                    90: cv2.ROTATE_90_CLOCKWISE,
                    180: cv2.ROTATE_180,
                    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
                }[self.cfg.camera.rotation],
            )
        if self.cfg.watermark_timestamp:
            cv2.putText(
                frame,
                time.strftime("%Y-%m-%d %H:%M:%S"),
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
        height, width = frame.shape[:2]
        for polygon in self.cfg.camera.privacy_masks:
            points = np.array([(int(x * width), int(y * height)) for x, y in polygon], np.int32)
            cv2.fillPoly(frame, [points], (0, 0, 0))
        return frame

    def motion_input(self, frame: np.ndarray) -> np.ndarray:
        if not self.cfg.camera.motion_zones:
            return frame
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        polygons = [
            np.array([(int(x * width), int(y * height)) for x, y in polygon], np.int32)
            for polygon in self.cfg.camera.motion_zones
        ]
        cv2.fillPoly(mask, polygons, 255)
        return cv2.bitwise_and(frame, frame, mask=mask)

    def begin(self, frame: np.ndarray, score: float) -> None:
        path = self.storage.recording_path(self.cfg.camera.name)
        working_path = path.with_name(path.stem + ".partial.mp4")
        h, w = frame.shape[:2]
        writer = cv2.VideoWriter(
            str(working_path),
            cv2.VideoWriter_fourcc(*self.cfg.features.encoder),  # type: ignore[attr-defined]
            self.cfg.camera.fps,
            (w, h),
        )
        if not writer.isOpened():
            writer.release()
            working_path.unlink(missing_ok=True)
            raise RuntimeError(self.trn.tr("recording.encoder_error"))
        self.path = path
        self.working_path = working_path
        self.writer = writer
        self.started = (
            self.buffer[0][0] if self.cfg.mode == "motion" and self.buffer else time.time()
        )
        self.thumbnail = frame.copy()
        for _, old in self.buffer:
            writer.write(old)
        self.storage.write_metadata(
            path,
            {
                "camera": self.cfg.camera.name,
                "started": self.started,
                "event": "motion" if self.cfg.mode == "motion" else self.cfg.mode,
                "motion_score": score,
                "protected": False,
            },
        )

    def finish(self) -> None:
        if self.writer:
            self.writer.release()
            self.writer = None
        path = self.path
        working_path = self.working_path
        thumbnail_frame = self.thumbnail
        if path is None:
            return
        try:
            if working_path and working_path.exists():
                working_path.replace(path)
            if not path.exists():
                log.error("recording working file disappeared before finalization: %s", path)
                return
            thumbnail = (
                self.storage.create_thumbnail(path, thumbnail_frame)
                if self.cfg.features.thumbnails and thumbnail_frame is not None
                else None
            )
            self.storage.write_metadata(
                path,
                {
                    "camera": self.cfg.camera.name,
                    "started": self.started,
                    "ended": time.time(),
                    "event": self.cfg.mode,
                    "protected": False,
                    "thumbnail": str(thumbnail) if thumbnail else None,
                    "encoder": self.cfg.features.encoder,
                    "sha256": file_sha256(path),
                },
            )
            if self.cfg.features.sync_directory:
                try:
                    self.storage.synchronize_recording(
                        path, Path(self.cfg.features.sync_directory).expanduser()
                    )
                except OSError as exc:
                    log.warning("recording synchronization failed: %s", exc)
                    self.status(sync_error=str(exc))
            self.last_finished = time.time()
        finally:
            self.path = None
            self.working_path = None
            self.thumbnail = None

    def run(self) -> int:
        delay = 1.0
        self.status(message_key="service.starting", message=self.trn.tr("service.starting"))
        try:
            while not self.stop.is_set() and not STOP.exists():
                if self.capture is None or not self.capture.isOpened():
                    if not self.connect():
                        self.status(
                            error_key="camera.unavailable", error=self.trn.tr("camera.unavailable")
                        )
                        self.stop.wait(delay)
                        delay = min(delay * 2, 30)
                        continue
                    delay = 1.0
                    self.status(
                        message_key="camera.connected", message=self.trn.tr("camera.connected")
                    )
                ok, raw = self.capture.read()
                if not ok:
                    self.finish()
                    self.capture.release()
                    self.capture = None
                    self.status(
                        error_key="camera.interrupted", error=self.trn.tr("camera.interrupted")
                    )
                    continue
                frame = self.transform(raw)
                now = time.time()
                if not schedule_active(self.cfg.schedule):
                    self.finish()
                    self.stop.wait(0.25)
                    continue
                motion, score = (
                    self.detector.detect(self.motion_input(frame))
                    if self.cfg.mode == "motion"
                    else (False, 0.0)
                )
                if self.cfg.mode == "continuous":
                    should = True
                elif self.cfg.mode == "manual":
                    should = MANUAL_RECORD.exists()
                else:
                    should = bool(
                        (
                            self.writer
                            and now - self.last_motion < self.cfg.motion.post_event_seconds
                        )
                        or (motion and now - self.last_finished >= self.cfg.motion.cooldown_seconds)
                    )
                if motion:
                    self.last_motion = now
                if should and self.writer is None:
                    self.begin(frame, score)
                if self.writer:
                    self.writer.write(frame)
                if self.cfg.mode == "motion":
                    self.buffer.append((now, frame.copy()))
                if self.writer and (
                    not should or now - self.started >= self.cfg.storage.segment_seconds
                ):
                    self.finish()
                    self.storage.cleanup()
                if now - self.last_status >= 2.0:
                    self.status(motion=motion, motion_score=round(score, 4))
                    self.last_status = now
            return 0
        finally:
            self.finish()
            if self.capture:
                self.capture.release()
            STOP.unlink(missing_ok=True)
            MANUAL_RECORD.unlink(missing_ok=True)
            self.status(
                running=False,
                camera_connected=False,
                recording=False,
                message_key="service.stopped",
                message=self.trn.tr("service.stopped"),
            )


def main() -> int:
    if not acquire_lock():
        print(Translator().tr("service.already_running"), file=sys.stderr)
        return 3
    try:
        clear_control_markers()
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        svc = Service(load())
        signal.signal(signal.SIGTERM, lambda *_: svc.stop.set())
        signal.signal(signal.SIGINT, lambda *_: svc.stop.set())
        try:
            return svc.run()
        except Exception:
            log.exception("fatal service error")
            return 1
    except Exception:
        log.exception("fatal service error")
        return 1
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
