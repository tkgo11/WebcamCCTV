"""Camera discovery and access testing."""

from __future__ import annotations
import cv2
from .i18n import Translator


def discover(limit: int = 10, language: str | None = None) -> list[dict[str, object]]:
    found = []
    tr = Translator(language)
    for index in range(limit):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                found.append(
                    {
                        "index": index,
                        "name": tr.tr("camera.default_name", index=index),
                        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                        "fps": cap.get(cv2.CAP_PROP_FPS),
                    }
                )
        cap.release()
    return found
