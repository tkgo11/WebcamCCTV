"""Recording metadata and bounded retention."""

from __future__ import annotations
from pathlib import Path
import json
import shutil
import time


class StorageManager:
    def __init__(
        self, root: Path, maximum_gib: float, retention_days: int, minimum_free_gib: float
    ) -> None:
        self.root = root
        self.max_bytes = int(maximum_gib * 1024**3)
        self.max_age = retention_days * 86400
        self.min_free = int(minimum_free_gib * 1024**3)
        root.mkdir(parents=True, exist_ok=True)

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
                total -= size
                deleted.append(p)
        return deleted
