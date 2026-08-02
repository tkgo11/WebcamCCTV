from webcamcctv import cameras


class FakeCapture:
    def __init__(self, index):
        self.index = index
        self.released = False

    def isOpened(self):
        return self.index != 1

    def read(self):
        return self.index == 0, object()

    def get(self, property_id):
        return {cameras.cv2.CAP_PROP_FRAME_WIDTH: 1280, cameras.cv2.CAP_PROP_FRAME_HEIGHT: 720}.get(
            property_id, 30
        )

    def release(self):
        self.released = True


def test_discovery_reports_only_readable_cameras_and_releases_every_handle(monkeypatch):
    handles = []

    def capture(index):
        handle = FakeCapture(index)
        handles.append(handle)
        return handle

    monkeypatch.setattr(cameras.cv2, "VideoCapture", capture)
    assert cameras.discover(limit=3, language="en") == [
        {"index": 0, "name": "Camera 0", "width": 1280, "height": 720, "fps": 30}
    ]
    assert all(handle.released for handle in handles)
