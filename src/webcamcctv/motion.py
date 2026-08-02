"""Efficient local motion detection."""

from __future__ import annotations

import cv2
import numpy as np


class MotionDetector:
    def __init__(self, sensitivity: float, minimum_area: int, warmup_frames: int = 5) -> None:
        self.sensitivity, self.minimum_area = sensitivity, minimum_area
        self.warmup_frames = max(0, warmup_frames)
        self.frames_seen = 0
        self.reset()

    def reset(self) -> None:
        self.background = cv2.createBackgroundSubtractorMOG2(
            history=400,
            varThreshold=max(8, 64 * (1 - self.sensitivity)),
            detectShadows=True,
        )
        self.frames_seen = 0

    def detect(self, frame: np.ndarray) -> tuple[bool, float]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)
        mask = self.background.apply(gray)
        mask[mask == 127] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        changed = int(cv2.countNonZero(mask))
        score = changed / float(mask.size)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self.frames_seen += 1
        detected = score >= self.sensitivity and any(
            cv2.contourArea(c) >= self.minimum_area for c in contours
        )
        return self.frames_seen > self.warmup_frames and detected, score
