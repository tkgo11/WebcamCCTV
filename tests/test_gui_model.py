from webcamcctv.gui_model import manual_record_controls


def test_manual_controls_follow_active_service_mode_and_recording_state():
    assert manual_record_controls({"running": False, "mode": "manual"}) == (False, False)
    assert manual_record_controls({"running": True, "mode": "motion"}) == (False, False)
    assert manual_record_controls({"running": True, "mode": "manual", "recording": False}) == (
        True,
        False,
    )
    assert manual_record_controls({"running": True, "mode": "manual", "recording": True}) == (
        False,
        True,
    )
