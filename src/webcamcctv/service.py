"""Headless capture service with reconnect, motion events and pre/post buffering."""

from __future__ import annotations
from collections import deque
from pathlib import Path
from threading import Event
from typing import Any
import json
import logging
import os
import signal
import sys
import time
import cv2
import numpy as np
from platformdirs import user_state_dir
from .config import AppConfig, load
from .motion import MotionDetector
from .storage import StorageManager
from .i18n import Translator
from .features import Notification, Notifier, schedule_active

STATE_DIR = Path(user_state_dir("WebcamCCTV"))
STATUS = STATE_DIR / "status.json"
STOP = STATE_DIR / "stop.request"
LOCK = STATE_DIR / "service.lock"
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
        self.notifier = Notifier()
        self.storage.reconcile()
        self.started = 0.0
        self.last_motion = 0.0
        self.buffer: deque[tuple[float, np.ndarray]] = deque(
            maxlen=max(1, int(cfg.camera.fps * cfg.motion.pre_event_seconds))
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

    def begin(self, frame: np.ndarray, score: float) -> None:
        self.path = self.storage.recording_path(self.cfg.camera.name)
        self.working_path = self.path.with_name(self.path.stem + ".partial.mp4")
        h, w = frame.shape[:2]
        self.writer = cv2.VideoWriter(
            str(self.working_path), cv2.VideoWriter_fourcc(*self.cfg.features.encoder),  # type: ignore[attr-defined]
            self.cfg.camera.fps, (w, h)
        )
        if not self.writer.isOpened():
            self.writer = None
            raise RuntimeError(self.trn.tr("recording.encoder_error"))
        self.started = time.time()
        self.thumbnail = frame.copy()
        for _, old in self.buffer:
            self.writer.write(old)
        self.storage.write_metadata(
            self.path,
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
        if self.path:
            if self.working_path and self.working_path.exists():
                self.working_path.replace(self.path)
            thumbnail = (
                self.storage.create_thumbnail(self.path, self.thumbnail)
                if self.cfg.features.thumbnails and self.thumbnail is not None else None
            )
            self.storage.write_metadata(
                self.path,
                {
                    "camera": self.cfg.camera.name,
                    "started": self.started,
                    "ended": time.time(),
                    "event": self.cfg.mode,
                    "protected": False,
                    "thumbnail": str(thumbnail) if thumbnail else None,
                    "encoder": self.cfg.features.encoder,
                },
            )
            if self.cfg.features.sync_directory:
                self.storage.synchronize(self.path, Path(self.cfg.features.sync_directory).expanduser())
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
                motion, score = self.detector.detect(frame)
                self.buffer.append((now, frame.copy()))
                should = self.cfg.mode == "continuous" or (
                    self.cfg.mode == "motion"
                    and (
                        motion
                        or (
                            self.writer
                            and now - self.last_motion < self.cfg.motion.post_event_seconds
                        )
                    )
                )
                if motion:
                    self.last_motion = now
                    if self.cfg.features.notifications:
                        self.notifier.send(Notification("motion", "Motion detected"), now)
                if should and self.writer is None:
                    self.begin(frame, score)
                if self.writer:
                    self.writer.write(frame)
                if self.writer and (
                    not should or now - self.started >= self.cfg.storage.segment_seconds
                ):
                    self.finish()
                    self.storage.cleanup()
                if int(now * 2) % 4 == 0:
                    self.status(motion=motion, motion_score=round(score, 4))
            return 0
        finally:
            self.finish()
            if self.capture:
                self.capture.release()
            STOP.unlink(missing_ok=True)
            self.status(
                running=False,
                camera_connected=False,
                recording=False,
                message_key="service.stopped",
                message=self.trn.tr("service.stopped"),
            )
            LOCK.unlink(missing_ok=True)


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            existing_pid = int(LOCK.read_text("ascii"))
            os.kill(existing_pid, 0)
        except (ValueError, ProcessLookupError, PermissionError):
            LOCK.unlink(missing_ok=True)
        else:
            print(Translator(load().language).tr("service.already_running"), file=sys.stderr)
            return 3
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        print(Translator(load().language).tr("service.startup_race"), file=sys.stderr)
        return 3
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    svc = Service(load())
    signal.signal(signal.SIGTERM, lambda *_: svc.stop.set())
    signal.signal(signal.SIGINT, lambda *_: svc.stop.set())
    try:
        return svc.run()
    except Exception:
        log.exception("fatal service error")
        LOCK.unlink(missing_ok=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
