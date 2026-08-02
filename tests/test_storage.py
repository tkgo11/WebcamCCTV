import json
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


def test_recording_paths_do_not_collide_with_existing_recording(tmp_path):
    storage = StorageManager(tmp_path, 1, 1, 0)
    first = storage.recording_path("cam", 1)
    first.touch()
    second = storage.recording_path("cam", 1)
    assert second != first and second.name.endswith("_001.mp4")


def test_reconcile_quarantines_partial_mp4_and_moves_metadata(tmp_path):
    storage = StorageManager(tmp_path, 1, 1, 0)
    final = storage.recording_path("cam", 1)
    partial = final.with_name(final.stem + ".partial.mp4")
    partial.write_bytes(b"partial")
    final.with_suffix(".json").write_text(
        json.dumps({"camera": "cam", "event": "motion", "started": 1}), encoding="utf-8"
    )
    storage.reconcile()
    interrupted = final.with_name(final.stem + ".interrupted.mp4")
    assert interrupted.read_bytes() == b"partial"
    assert not partial.exists() and not final.with_suffix(".json").exists()
    assert json.loads(interrupted.with_suffix(".json").read_text("utf-8"))["event"] == "interrupted"


def test_sync_preserves_dated_path_and_companions(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    storage = StorageManager(source, 1, 1, 0)
    video = storage.recording_path("cam", 1)
    video.write_bytes(b"video")
    storage.write_metadata(video, {"camera": "cam", "started": 1})
    video.with_suffix(".jpg").write_bytes(b"thumb")
    copied = storage.synchronize_recording(video, destination)
    assert len(copied) == 3
    assert (destination / video.relative_to(source)).read_bytes() == b"video"


def test_cleanup_never_deletes_active_partial_file(tmp_path):
    storage = StorageManager(
        tmp_path, maximum_gib=0.000000001, retention_days=1, minimum_free_gib=0
    )
    partial = storage.recording_path("cam", 1).with_name("active.partial.mp4")
    partial.write_bytes(b"active")
    os.utime(partial, (1, 1))
    assert storage.cleanup(now=time.time()) == []
    assert partial.exists()
