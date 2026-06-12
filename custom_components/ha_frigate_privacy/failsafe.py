"""Pure fail-safe decisions for Frigate Privacy resume exits."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _stable_list(values: Iterable[str] | None) -> list[str]:
    """Return a sorted de-duplicated string list."""
    if not values:
        return []
    return sorted({str(value) for value in values if value})


def decide_resume_exit(
    *,
    attempted: Iterable[str] | None,
    unavailable: Iterable[str] | None,
    failed: Iterable[str] | None,
) -> dict[str, Any]:
    """Decide whether a privacy window may be cleared after resume.

    Privacy-first rule: any uncertainty while exiting a privacy window keeps
    the camera marked paused and requires a persistent notification. Missing
    or unavailable switches block auto-resume before toggling. Service failures
    after toggling also keep the paused state so the user can retry explicitly.
    """
    attempted_list = _stable_list(attempted)
    unavailable_list = _stable_list(unavailable)
    failed_list = _stable_list(failed)

    if unavailable_list:
        return {
            "clear_paused": False,
            "keep_paused": True,
            "notification_required": True,
            "reason": "switch_unavailable",
            "attempted": attempted_list,
            "unavailable": unavailable_list,
            "failed": failed_list,
        }

    if failed_list:
        return {
            "clear_paused": False,
            "keep_paused": True,
            "notification_required": True,
            "reason": "resume_failed",
            "attempted": attempted_list,
            "unavailable": unavailable_list,
            "failed": failed_list,
        }

    return {
        "clear_paused": True,
        "keep_paused": False,
        "notification_required": False,
        "reason": None,
        "attempted": attempted_list,
        "unavailable": unavailable_list,
        "failed": failed_list,
    }
