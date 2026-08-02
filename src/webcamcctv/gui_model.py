"""Pure presentation-state helpers for the desktop monitor."""

from __future__ import annotations


def manual_record_controls(service_data: dict[str, object]) -> tuple[bool, bool]:
    """Return whether manual recording may be started and stopped."""
    manual_service = bool(service_data.get("running")) and service_data.get("mode") == "manual"
    recording = bool(service_data.get("recording"))
    return manual_service and not recording, manual_service and recording
