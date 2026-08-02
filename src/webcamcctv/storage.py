"""Recording metadata and bounded retention."""

from __future__ import annotations
from pathlib import Path
import json
import shutil
import time
import sqlite3
import hashlib
import os
from typing import Any


class StorageManager:
    def __init__(
        self, root: Path, maximum_gib: float, retention_days: int, minimum_free_gib: float
    ) -> None:
        self.root = root
        self.max_bytes = int(maximum_gib * 1024**3)
        self.max_age = retention_days * 86400
        self.min_free = int(minimum_free_gib * 1024**3)
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / "recordings.sqlite3"
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS recordings
                (path TEXT PRIMARY KEY, started REAL, ended REAL, camera TEXT, event TEXT,
                 protected INTEGER DEFAULT 0, thumbnail TEXT, sha256 TEXT)""")

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database, timeout=10)

    def recording_path(self, camera: str, now: float | None = None) -> Path:
        stamp = time.localtime(now)
        folder = self.root / time.strftime("%Y/%m/%d", stamp)
        folder.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in camera if c.isalnum() or c in "-_ ").strip() or "camera"
        return folder / f"{time.strftime('%Y%m%d_%H%M%S', stamp)}_{safe}.mp4"

    def write_metadata(self, video: Path, data: dict[str, object]) -> None:
        temp = video.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
        temp.replace(video.with_suffix(".json"))
        with self._db() as db:
            db.execute(
                """INSERT INTO recordings(path,started,ended,camera,event,protected,thumbnail,sha256)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET ended=excluded.ended,
                camera=excluded.camera,event=excluded.event,protected=excluded.protected,
                thumbnail=excluded.thumbnail,sha256=excluded.sha256""",
                (str(video), data.get("started"), data.get("ended"), data.get("camera"),
                 data.get("event"), int(bool(data.get("protected"))), data.get("thumbnail"),
                 data.get("sha256")),
            )

    def create_thumbnail(self, video: Path, frame: Any) -> Path | None:
        import cv2
        target = video.with_suffix(".jpg")
        return target if cv2.imwrite(str(target), frame, [cv2.IMWRITE_JPEG_QUALITY, 78]) else None

    def snapshot_path(self, camera: str, now: float | None = None) -> Path:
        return self.recording_path(camera, now).with_suffix(".jpg")

    def reconcile(self) -> int:
        """Import sidecars and quarantine interrupted working files."""
        count = 0
        for sidecar in self.root.rglob("*.json"):
            try:
                self.write_metadata(sidecar.with_suffix(".mp4"), json.loads(sidecar.read_text("utf-8")))
                count += 1
            except (OSError, ValueError, TypeError):
                continue
        for partial in self.root.rglob("*.partial"):
            partial.rename(partial.with_suffix(".interrupted"))
        return count

    def synchronize(self, video: Path, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / video.name
        temp = target.with_suffix(target.suffix + ".tmp")
        shutil.copy2(video, temp)
        if hashlib.sha256(temp.read_bytes()).digest() != hashlib.sha256(video.read_bytes()).digest():
            temp.unlink(missing_ok=True)
            raise OSError("synchronization checksum mismatch")
        os.replace(temp, target)
        return target

    def cleanup(self, now: float | None = None) -> list[Path]:
        now = now or time.time()
        files = sorted(self.root.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        deleted = []
        for p in files:
            protected = p.with_suffix(".protected").exists()
            pressure = total > self.max_bytes or shutil.disk_usage(self.root).free < self.min_free
            expired = now - p.stat().st_mtime > self.max_age
            if not protected and (pressure or expired):
                size = p.stat().st_size
                p.unlink(missing_ok=True)
                p.with_suffix(".json").unlink(missing_ok=True)
                p.with_suffix(".jpg").unlink(missing_ok=True)
                with self._db() as db:
                    db.execute("DELETE FROM recordings WHERE path=?", (str(p),))
                total -= size
                deleted.append(p)
        return deleted
