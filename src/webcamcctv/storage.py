"""Recording metadata and bounded retention."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
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
        safe = "".join(c for c in camera if c.isalnum() or c in "-_ ").strip()[:80].rstrip()
        safe = safe or "camera"
        stem = f"{time.strftime('%Y%m%d_%H%M%S', stamp)}_{safe}"
        candidate = folder / f"{stem}.mp4"
        sequence = 1
        while (
            candidate.exists()
            or candidate.with_suffix(".json").exists()
            or candidate.with_name(candidate.stem + ".partial.mp4").exists()
        ):
            candidate = folder / f"{stem}_{sequence:03d}.mp4"
            sequence += 1
        return candidate

    def write_metadata(self, video: Path, data: dict[str, object]) -> None:
        target = video.with_suffix(".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{target.stem}-", suffix=".json", dir=target.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        with self._db() as db:
            db.execute(
                """INSERT INTO recordings(path,started,ended,camera,event,protected,thumbnail,sha256)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET ended=excluded.ended,
                camera=excluded.camera,event=excluded.event,protected=excluded.protected,
                thumbnail=excluded.thumbnail,sha256=excluded.sha256""",
                (
                    str(video),
                    data.get("started"),
                    data.get("ended"),
                    data.get("camera"),
                    data.get("event"),
                    int(bool(data.get("protected"))),
                    data.get("thumbnail"),
                    data.get("sha256"),
                ),
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
        for partial in self.root.rglob("*.partial.mp4"):
            interrupted_mtime = partial.stat().st_mtime
            base_name = partial.name.removesuffix(".partial.mp4")
            interrupted = partial.with_name(f"{base_name}.interrupted.mp4")
            sequence = 1
            while interrupted.exists():
                interrupted = partial.with_name(f"{base_name}.interrupted-{sequence:03d}.mp4")
                sequence += 1
            partial.rename(interrupted)
            original_sidecar = partial.with_name(f"{base_name}.json")
            if original_sidecar.exists():
                try:
                    data = json.loads(original_sidecar.read_text("utf-8"))
                    if isinstance(data, dict):
                        data.update(event="interrupted", ended=interrupted_mtime)
                        self.write_metadata(interrupted, data)
                        original_sidecar.unlink(missing_ok=True)
                except (OSError, ValueError, TypeError):
                    pass
        for sidecar in self.root.rglob("*.json"):
            try:
                video = sidecar.with_suffix(".mp4")
                data = json.loads(sidecar.read_text("utf-8"))
                if not video.exists() or not isinstance(data, dict):
                    continue
                self.write_metadata(video, data)
                count += 1
            except (OSError, ValueError, TypeError):
                continue
        return count

    def synchronize(self, video: Path, directory: Path) -> Path:
        relative = video.relative_to(self.root)
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        try:
            shutil.copy2(video, temp)
            if file_sha256(temp) != file_sha256(video):
                raise OSError("synchronization checksum mismatch")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return target

    def synchronize_recording(self, video: Path, directory: Path) -> list[Path]:
        synchronized = [self.synchronize(video, directory)]
        for companion in (video.with_suffix(".json"), video.with_suffix(".jpg")):
            if companion.exists():
                synchronized.append(self.synchronize(companion, directory))
        return synchronized

    def cleanup(self, now: float | None = None) -> list[Path]:
        now = time.time() if now is None else now
        files = sorted(
            (path for path in self.root.rglob("*.mp4") if not path.name.endswith(".partial.mp4")),
            key=lambda path: path.stat().st_mtime,
        )
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
