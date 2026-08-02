import numpy as np

from webcamcctv.motion import MotionDetector


def test_static_frame_settles_without_motion():
    d = MotionDetector(0.04, 50)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    for _ in range(20):
        result, _ = d.detect(frame)
    assert result is False


def test_warmup_suppresses_initial_full_frame_event():
    detector = MotionDetector(0.01, 1, warmup_frames=2)
    frame = np.full((120, 160, 3), 255, dtype=np.uint8)
    assert detector.detect(frame)[0] is False
    assert detector.detect(frame)[0] is False
