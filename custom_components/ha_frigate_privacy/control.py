"""Frigate camera discovery and privacy switch control."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN, EVENT_STATE_CHANGED
from .failsafe import decide_resume_exit
from .storage import FrigatePrivacyStorage

_LOGGER = logging.getLogger(__name__)

LEGACY_SUFFIXES = (
    "_enabled",
    "_detect",
    "_recordings",
    "_snapshots",
    "_motion",
    "_audio",
)
CURRENT_SUFFIXES = (
    "_detect",
    "_recordings",
    "_snapshots",
    "_motion",
    "_audio_detection",
    "_review_alerts",
    "_review_detections",
)
ALL_SUFFIXES = tuple(dict.fromkeys((*LEGACY_SUFFIXES, *CURRENT_SUFFIXES)))
DISCOVERY_SUFFIXES = ("_detect", "_recordings")
UNAVAILABLE_STATES = {"unavailable", "unknown"}


def camera_base(value: str) -> str:
    """Return the Frigate camera base id for a camera/switch/base value."""
    item = str(value or "").strip()
    if item.startswith("camera."):
        return item.split(".", 1)[1]
    if item.startswith("switch."):
        item = item.split(".", 1)[1]
        for suffix in sorted(ALL_SUFFIXES, key=len, reverse=True):
            if item.endswith(suffix):
                return item[: -len(suffix)]
    return item


def camera_entity_id(hass: HomeAssistant, base: str) -> str | None:
    """Return the matching camera entity id when Home Assistant has one."""
    entity_id = f"camera.{base}"
    return entity_id if hass.states.get(entity_id) is not None else None


def suffixes_for_stream_type(stream_type: str | None) -> tuple[str, ...]:
    """Return Frigate switch suffixes for all/main/sub privacy modes."""
    if stream_type == "main":
        return ("_recordings", "_snapshots")
    if stream_type == "sub":
        return ("_detect", "_motion", "_audio", "_audio_detection")
    return ALL_SUFFIXES


def discover_frigate_cameras(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Discover Frigate cameras from switch.<cam>_detect/_recordings entities."""
    bases: set[str] = set()
    for entity_id in hass.states.async_entity_ids("switch"):
        name = entity_id.split(".", 1)[1]
        for suffix in DISCOVERY_SUFFIXES:
            if name.endswith(suffix):
                bases.add(name[: -len(suffix)])
                break

    cameras: list[dict[str, Any]] = []
    for base in sorted(bases):
        cam_entity = camera_entity_id(hass, base)
        state = hass.states.get(cam_entity) if cam_entity else None
        switches = _switches_for_base(hass, base, ALL_SUFFIXES)
        cameras.append(
            {
                "camera_id": base,
                "entity_id": cam_entity,
                "name": (
                    state.attributes.get("friendly_name")
                    if state is not None
                    else base.replace("_", " ").title()
                ),
                "switches": switches,
                "available_switches": [item["entity_id"] for item in switches],
                "missing_switches": [
                    f"switch.{base}{suffix}"
                    for suffix in ALL_SUFFIXES
                    if hass.states.get(f"switch.{base}{suffix}") is None
                ],
            }
        )
    return cameras


async def async_pause_cameras(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_refs: list[str] | None,
    *,
    duration_minutes: int | None = None,
    stream_type: str = "all",
    source: str = "manual",
    schedule_id: str | None = None,
) -> dict[str, Any]:
    """Pause selected or all discovered Frigate cameras."""
    refs = camera_refs or [item["camera_id"] for item in discover_frigate_cameras(hass)]
    results = []
    for ref in refs:
        results.append(
            await async_pause_camera(
                hass,
                storage,
                ref,
                duration_minutes=duration_minutes,
                stream_type=stream_type,
                source=source,
                schedule_id=schedule_id,
            )
        )
    return {"results": results, "ok": any(item["paused"] for item in results)}


async def async_pause_camera(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_ref: str,
    *,
    duration_minutes: int | None = None,
    stream_type: str = "all",
    source: str = "manual",
    schedule_id: str | None = None,
) -> dict[str, Any]:
    """Pause one camera by turning off every existing compatible switch."""
    base = camera_base(camera_ref)
    cam_entity = camera_entity_id(hass, base)
    suffixes = suffixes_for_stream_type(stream_type)
    switches = _switches_for_base(hass, base, suffixes)
    missing = [
        f"switch.{base}{suffix}"
        for suffix in suffixes
        if hass.states.get(f"switch.{base}{suffix}") is None
    ]
    skipped: list[str] = list(missing)
    failed: list[str] = []
    toggled: list[str] = []
    camera_toggled = False
    camera_failed = False

    for item in switches:
        entity_id = item["entity_id"]
        state = hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE_STATES:
            skipped.append(entity_id)
            continue
        try:
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": entity_id}, blocking=True
            )
            toggled.append(entity_id)
        except Exception as err:  # noqa: BLE001 - surface in result
            _LOGGER.warning("Failed to pause %s: %s", entity_id, err)
            failed.append(entity_id)

    if stream_type == "all" and cam_entity:
        try:
            await hass.services.async_call(
                "camera", "turn_off", {"entity_id": cam_entity}, blocking=True
            )
            camera_toggled = True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to stop camera stream %s: %s", cam_entity, err)
            camera_failed = True

    paused = bool(toggled or camera_toggled)
    if paused:
        now = datetime.now(timezone.utc)
        ends_at = (
            now + timedelta(minutes=duration_minutes)
            if duration_minutes is not None
            else None
        )
        await storage.async_set_paused(
            base,
            {
                "camera_entity_id": cam_entity,
                "name": _camera_name(hass, cam_entity, base),
                "stream_type": stream_type,
                "source": source,
                "schedule_id": schedule_id,
                "switches": toggled,
                "skipped": skipped,
                "failed": failed,
                "camera_toggled": camera_toggled,
                "camera_failed": camera_failed,
                "started_at": now.isoformat(),
                "ends_at": ends_at.isoformat() if ends_at else None,
                "resume_blocked": False,
            },
        )
        hass.bus.async_fire(EVENT_STATE_CHANGED, {"camera_id": base})

    return {
        "camera_id": base,
        "camera_entity_id": cam_entity,
        "paused": paused,
        "switches": toggled,
        "skipped": skipped,
        "failed": failed,
        "camera_toggled": camera_toggled,
        "camera_failed": camera_failed,
    }


async def async_resume_cameras(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_refs: list[str] | None,
    *,
    automatic: bool = False,
) -> dict[str, Any]:
    """Resume selected or all paused cameras."""
    paused_all = await storage.async_get_paused(None)
    refs = camera_refs or list((paused_all or {}).keys())
    if not refs:
        refs = [item["camera_id"] for item in discover_frigate_cameras(hass)]
    results = []
    for ref in refs:
        results.append(
            await async_resume_camera(hass, storage, ref, automatic=automatic)
        )
    return {"results": results, "ok": all(item["resumed"] for item in results)}


async def async_resume_camera(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_ref: str,
    *,
    automatic: bool = False,
) -> dict[str, Any]:
    """Resume one camera with privacy-first fail-safe semantics."""
    base = camera_base(camera_ref)
    paused = await storage.async_get_paused(base)
    if not paused:
        return {
            "camera_id": base,
            "resumed": True,
            "nothing_to_resume": True,
            "fail_safe": False,
        }

    expected = list(paused.get("switches") or [])
    cam_entity = paused.get("camera_entity_id") or camera_entity_id(hass, base)
    unavailable = [
        entity_id
        for entity_id in expected
        if _state_unavailable(hass, entity_id)
    ]
    if paused.get("camera_toggled") and cam_entity and _state_unavailable(
        hass, cam_entity
    ):
        unavailable.append(cam_entity)

    preflight = decide_resume_exit(
        attempted=expected,
        unavailable=unavailable,
        failed=[],
    )
    if not preflight["clear_paused"]:
        await _hold_fail_safe(hass, storage, base, paused, preflight)
        return _resume_result(base, False, preflight, automatic)

    failed: list[str] = []
    turned_on: list[str] = []
    camera_turned_on = False
    try:
        if paused.get("camera_toggled") and cam_entity:
            await hass.services.async_call(
                "camera", "turn_on", {"entity_id": cam_entity}, blocking=True
            )
            camera_turned_on = True
        for entity_id in expected:
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": entity_id}, blocking=True
            )
            turned_on.append(entity_id)
    except Exception as err:  # noqa: BLE001 - fail-safe branch
        failed.append(entity_id if "entity_id" in locals() else cam_entity or base)
        _LOGGER.warning("Resume failed for %s: %s", failed[-1], err)

    decision = decide_resume_exit(
        attempted=expected,
        unavailable=[],
        failed=failed,
    )
    if decision["clear_paused"]:
        await storage.async_clear_paused(base)
        hass.bus.async_fire(EVENT_STATE_CHANGED, {"camera_id": base})
        return _resume_result(base, True, decision, automatic)

    # Explicit fail-safe: if a resume call fails after any successful turn_on,
    # immediately try to restore the paused/off state, keep storage active, and
    # notify. We never clear paused state on uncertainty.
    await _restore_pause_after_failed_resume(
        hass, turned_on, cam_entity if camera_turned_on else None
    )
    await _hold_fail_safe(hass, storage, base, paused, decision)
    return _resume_result(base, False, decision, automatic)


def _switches_for_base(
    hass: HomeAssistant, base: str, suffixes: tuple[str, ...]
) -> list[dict[str, Any]]:
    switches = []
    for suffix in suffixes:
        entity_id = f"switch.{base}{suffix}"
        state = hass.states.get(entity_id)
        if state is None:
            continue
        switches.append(
            {
                "entity_id": entity_id,
                "suffix": suffix,
                "state": state.state,
                "name": state.attributes.get("friendly_name") or entity_id,
            }
        )
    return switches


def _camera_name(hass: HomeAssistant, cam_entity: str | None, base: str) -> str:
    state = hass.states.get(cam_entity) if cam_entity else None
    if state is not None:
        return state.attributes.get("friendly_name") or cam_entity or base
    return base.replace("_", " ").title()


def _state_unavailable(hass: HomeAssistant, entity_id: str) -> bool:
    state = hass.states.get(entity_id)
    return state is None or state.state in UNAVAILABLE_STATES


async def _restore_pause_after_failed_resume(
    hass: HomeAssistant, switches: list[str], camera_entity: str | None
) -> None:
    for entity_id in switches:
        try:
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": entity_id}, blocking=True
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Fail-safe re-pause failed for %s: %s", entity_id, err)
    if camera_entity:
        try:
            await hass.services.async_call(
                "camera", "turn_off", {"entity_id": camera_entity}, blocking=True
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Fail-safe camera stream re-pause failed for %s: %s",
                camera_entity,
                err,
            )


async def _hold_fail_safe(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_id: str,
    paused: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    await storage.async_mark_resume_blocked(
        camera_id,
        reason=str(decision["reason"]),
        failed=decision["failed"],
        unavailable=decision["unavailable"],
    )
    await _notify_resume_failed(hass, paused, decision)
    hass.bus.async_fire(EVENT_STATE_CHANGED, {"camera_id": camera_id})


async def _notify_resume_failed(
    hass: HomeAssistant, paused: dict[str, Any], decision: dict[str, Any]
) -> None:
    name = paused.get("name") or paused.get("camera_id") or "camera"
    camera_id = paused.get("camera_id") or camera_base(name)
    detail = ", ".join(decision["unavailable"] or decision["failed"])
    message = (
        f"Frigate Privacy did not exit the privacy window for {name}. "
        "The camera remains marked paused because resume was uncertain. "
        f"Reason: {decision['reason']}. Affected entities: {detail or 'unknown'}. "
        "Check the entities and resume manually when safe."
    )
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": f"{DOMAIN}_resume_failed_{camera_id}",
                "title": "Frigate Privacy resume blocked",
                "message": message,
            },
            blocking=False,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not create fail-safe notification: %s", err)


def _resume_result(
    camera_id: str, resumed: bool, decision: dict[str, Any], automatic: bool
) -> dict[str, Any]:
    return {
        "camera_id": camera_id,
        "resumed": resumed,
        "automatic": automatic,
        "fail_safe": not resumed,
        "decision": decision,
    }
