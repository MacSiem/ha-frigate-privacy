"""Pure fail-safe assertions for Frigate Privacy resume exits."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILSAFE_PATH = ROOT / "custom_components" / "ha_frigate_privacy" / "failsafe.py"
SPEC = importlib.util.spec_from_file_location("ha_frigate_privacy_failsafe", FAILSAFE_PATH)
assert SPEC and SPEC.loader
failsafe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(failsafe)

decide_resume_exit = failsafe.decide_resume_exit


def test_resume_success_can_clear_paused_state() -> None:
    decision = decide_resume_exit(
        attempted=["switch.front_detect", "switch.front_recordings"],
        unavailable=[],
        failed=[],
    )

    assert decision["clear_paused"] is True
    assert decision["keep_paused"] is False
    assert decision["notification_required"] is False


def test_resume_failure_keeps_camera_paused_and_notifies() -> None:
    decision = decide_resume_exit(
        attempted=["switch.front_detect", "switch.front_recordings"],
        unavailable=[],
        failed=["switch.front_recordings"],
    )

    assert decision["clear_paused"] is False
    assert decision["keep_paused"] is True
    assert decision["notification_required"] is True
    assert decision["reason"] == "resume_failed"
    assert decision["failed"] == ["switch.front_recordings"]


def test_unavailable_switch_blocks_auto_resume_before_toggling() -> None:
    decision = decide_resume_exit(
        attempted=["switch.front_detect", "switch.front_recordings"],
        unavailable=["switch.front_recordings"],
        failed=[],
    )

    assert decision["clear_paused"] is False
    assert decision["keep_paused"] is True
    assert decision["notification_required"] is True
    assert decision["reason"] == "switch_unavailable"
    assert decision["unavailable"] == ["switch.front_recordings"]


if __name__ == "__main__":
    test_resume_success_can_clear_paused_state()
    test_resume_failure_keeps_camera_paused_and_notifies()
    test_unavailable_switch_blocks_auto_resume_before_toggling()
    print("fail-safe assertions passed")
