import os
import time
from webcamcctv.storage import StorageManager


def test_retention_deletes_expired_but_not_protected(tmp_path):
    s = StorageManager(tmp_path, 1, 1, 0)
    old = s.recording_path("cam", 1)
    old.write_bytes(b"x")
    os.utime(old, (1, 1))
    protected = s.recording_path("cam", 2)
    protected.write_bytes(b"y")
    protected.with_suffix(".protected").touch()
    os.utime(protected, (1, 1))
    deleted = s.cleanup(now=time.time())
    assert old in deleted and not old.exists() and protected.exists()


def test_safe_camera_filename(tmp_path):
    s = StorageManager(tmp_path, 1, 1, 0)
    assert ".." not in s.recording_path("../../etc/passwd", 1).name
