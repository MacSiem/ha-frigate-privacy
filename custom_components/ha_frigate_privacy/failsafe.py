"""Pure fail-safe decisions for Frigate Privacy resume exits."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

#: Seconds after pause start during which 'on' switch states are attributed to
#: MQTT/Frigate confirmation lag rather than a manual override.
OVERRIDE_GRACE_SECONDS = 90


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


def decide_manual_override(
    *,
    started_at: datetime | None,
    now: datetime,
    switch_states: Mapping[str, str | None],
    grace_seconds: int = OVERRIDE_GRACE_SECONDS,
) -> dict[str, Any]:
    """Decide whether an active pause was overridden outside the integration.

    A pause is considered manually overridden when, past a short grace period
    after it started (MQTT/Frigate confirmation lag), at least one of the
    switches it turned off reports ``on`` again. ``unavailable``/``unknown``/
    missing states never count as an override — only a positive ``on`` does.
    """
    on_switches = _stable_list(
        entity_id
        for entity_id, state in switch_states.items()
        if state == "on"
    )

    in_grace = False
    if started_at is not None:
        elapsed = (now - started_at).total_seconds()
        in_grace = elapsed < grace_seconds

    return {
        "override": bool(on_switches) and not in_grace,
        "in_grace": in_grace,
        "on_switches": on_switches,
    }
