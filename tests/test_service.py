import json

import numpy as np

from webcamcctv.config import AppConfig
from webcamcctv.service import Service


class FakeWriter:
    def __init__(self, path, *_args):
        self.path = path
        self.frames = []
        self.opened = True
        with open(path, "wb") as stream:
            stream.write(b"video")

    def isOpened(self):
        return self.opened

    def write(self, frame):
        self.frames.append(frame.copy())

    def release(self):
        self.opened = False


def test_segment_starts_with_prebuffer_without_duplicating_current_frame(monkeypatch, tmp_path):
    config = AppConfig()
    config.storage.directory = str(tmp_path)
    config.features.thumbnails = False
    service = Service(config)
    monkeypatch.setattr("webcamcctv.service.cv2.VideoWriter", FakeWriter)
    monkeypatch.setattr("webcamcctv.service.cv2.VideoWriter_fourcc", lambda *_: 0)
    old = np.zeros((8, 8, 3), dtype=np.uint8)
    current = np.ones((8, 8, 3), dtype=np.uint8)
    service.buffer.append((1.0, old))

    service.begin(current, 0.5)
    writer = service.writer
    assert writer is not None and len(writer.frames) == 1
    writer.write(current)
    assert len(writer.frames) == 2
    service.finish()

    videos = list(tmp_path.rglob("*.mp4"))
    assert len(videos) == 1
    metadata = json.loads(videos[0].with_suffix(".json").read_text("utf-8"))
    assert metadata["sha256"] and metadata["started"] == 1.0


def test_motion_zones_black_out_pixels_outside_selected_area(tmp_path):
    config = AppConfig()
    config.storage.directory = str(tmp_path)
    config.camera.motion_zones = [[[0, 0], [0.5, 0], [0, 0.5]]]
    service = Service(config)
    frame = np.full((100, 100, 3), 255, dtype=np.uint8)
    selected = service.motion_input(frame)
    assert selected[5, 5].all()
    assert not selected[90, 90].any()


def test_continuous_run_captures_and_finalizes_without_hardware(monkeypatch, tmp_path):
    import webcamcctv.service as service_module

    config = AppConfig(mode="continuous", watermark_timestamp=False)
    config.storage.directory = str(tmp_path / "recordings")
    config.features.thumbnails = False
    service = Service(config)

    class FakeCapture:
        def __init__(self):
            self.opened = True

        def set(self, *_args):
            return True

        def isOpened(self):
            return self.opened

        def read(self):
            service.stop.set()
            return True, np.zeros((8, 8, 3), dtype=np.uint8)

        def release(self):
            self.opened = False

    state_dir = tmp_path / "state"
    monkeypatch.setattr(service_module, "STATE_DIR", state_dir)
    monkeypatch.setattr(service_module, "STATUS", state_dir / "status.json")
    monkeypatch.setattr(service_module, "STOP", state_dir / "stop.request")
    monkeypatch.setattr(service_module, "MANUAL_RECORD", state_dir / "manual-record.request")
    monkeypatch.setattr(service_module.cv2, "VideoCapture", lambda _device: FakeCapture())
    monkeypatch.setattr(service_module.cv2, "VideoWriter", FakeWriter)
    monkeypatch.setattr(service_module.cv2, "VideoWriter_fourcc", lambda *_: 0)

    assert service.run() == 0
    assert len(list((tmp_path / "recordings").rglob("*.mp4"))) == 1
    assert json.loads((state_dir / "status.json").read_text("utf-8"))["running"] is False
