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


# --- decide_manual_override -------------------------------------------------

from datetime import datetime, timedelta, timezone

decide_manual_override = failsafe.decide_manual_override
_NOW = datetime(2026, 7, 12, 19, 0, 0, tzinfo=timezone.utc)


def test_override_detected_after_grace_when_switch_back_on() -> None:
    decision = decide_manual_override(
        started_at=_NOW - timedelta(minutes=10),
        now=_NOW,
        switch_states={
            "switch.cam_detect": "on",
            "switch.cam_recordings": "off",
        },
    )
    assert decision["override"] is True
    assert decision["on_switches"] == ["switch.cam_detect"]
    assert decision["in_grace"] is False


def test_no_override_within_grace_period() -> None:
    decision = decide_manual_override(
        started_at=_NOW - timedelta(seconds=30),
        now=_NOW,
        switch_states={"switch.cam_detect": "on"},
    )
    assert decision["override"] is False
    assert decision["in_grace"] is True
    assert decision["on_switches"] == ["switch.cam_detect"]


def test_unavailable_and_unknown_states_never_count_as_override() -> None:
    decision = decide_manual_override(
        started_at=_NOW - timedelta(hours=1),
        now=_NOW,
        switch_states={
            "switch.cam_detect": "unavailable",
            "switch.cam_recordings": "unknown",
            "switch.cam_motion": None,
            "switch.cam_snapshots": "off",
        },
    )
    assert decision["override"] is False
    assert decision["on_switches"] == []


def test_missing_started_at_still_detects_override() -> None:
    decision = decide_manual_override(
        started_at=None,
        now=_NOW,
        switch_states={"switch.cam_detect": "on"},
    )
    assert decision["override"] is True
    assert decision["in_grace"] is False
