"""Frigate camera discovery and privacy switch control."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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
MAX_OPERATION_HISTORY = 16


class ResumeAuthority(StrEnum):
    """Explicit authority classes allowed to end a privacy pause."""

    ADMIN = "admin"
    DEADLINE = "deadline"
    RECOVERY = "recovery"
    SCHEDULE = "schedule"


def _camera_lock(storage: FrigatePrivacyStorage, camera_id: str) -> asyncio.Lock:
    """Return the per-storage, per-camera transition lock."""
    locks = getattr(storage, "_transition_locks", None)
    if locks is None:
        locks = {}
        setattr(storage, "_transition_locks", locks)
    return locks.setdefault(camera_id, asyncio.Lock())


def _discovered_camera_ids(hass: HomeAssistant) -> set[str]:
    """Return the exact current camera allowlist."""
    return {item["camera_id"] for item in discover_frigate_cameras(hass)}


def _is_frigate_entity(hass: HomeAssistant, entity_id: str) -> bool:
    """Return whether an entity registry entry belongs to Frigate."""
    entry = er.async_get(hass).async_get(entity_id)
    return bool(entry and entry.platform == "frigate")


def _new_operation_id(action: str, camera_id: str) -> str:
    """Return an opaque operation identifier safe to expose in state."""
    return f"{action}-{camera_id}-{uuid.uuid4().hex}"


def _scoped_operation_id(operation_id: str | None, camera_ref: str) -> str | None:
    """Scope a client operation id to one camera without exceeding the API cap."""
    if not operation_id:
        return None
    camera_digest = uuid.uuid5(
        uuid.NAMESPACE_URL, camera_base(camera_ref)
    ).hex[:12]
    suffix = f":{camera_digest}"
    return f"{operation_id[: 128 - len(suffix)]}{suffix}"


async def _latest_record(
    storage: FrigatePrivacyStorage, camera_id: str
) -> dict[str, Any] | None:
    """Return active or terminal evidence for idempotency checks."""
    getter = getattr(storage, "async_get_record", None)
    if getter is not None:
        return await getter(camera_id)
    try:
        return await storage.async_get_paused(camera_id, include_inactive=True)
    except TypeError:
        return await storage.async_get_paused(camera_id)


async def _reserve_camera_operation(
    storage: FrigatePrivacyStorage,
    camera_id: str,
    action: str,
    operation_id: str,
    history: list[dict[str, Any]],
) -> bool:
    """Reserve an operation before side effects, including for test doubles."""
    reserve = getattr(storage, "async_reserve_camera_operation", None)
    if reserve is not None:
        return await reserve(
            camera_id,
            action,
            operation_id,
            history=history,
        )

    # Legacy storage doubles do not have the durable filter. Keep a monotonic
    # in-memory tombstone so unit-level callers still fail closed on replays.
    seen = getattr(storage, "_camera_operation_tombstones", None)
    if seen is None:
        seen = {
            (
                camera_id,
                str(item.get("action")),
                str(item.get("id")),
            )
            for item in history
            if item.get("action") and item.get("id")
        }
        setattr(storage, "_camera_operation_tombstones", seen)
    key = (camera_id, action, operation_id)
    if key in seen:
        return False
    seen.add(key)
    return True


def _expired_operation_result(
    camera_id: str,
    *,
    action: str,
    operation_id: str,
    current_generation: int,
) -> dict[str, Any]:
    """Return a privacy-safe result when exact replay evidence was evicted."""
    result = _stale_operation_result(
        camera_id,
        action=action,
        operation_id=operation_id,
        current_generation=current_generation,
    )
    result["reason"] = "operation_history_expired"
    decision = result.get("decision")
    if isinstance(decision, dict):
        decision["reason"] = "operation_history_expired"
    return result


def _operation_history(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return a bounded, validated copy of the per-camera operation ledger."""
    if not record:
        return []
    history = record.get("operation_history") or []
    return [deepcopy(item) for item in history if isinstance(item, dict)][
        -MAX_OPERATION_HISTORY:
    ]


def _find_operation(
    record: dict[str, Any] | None,
    operation_id: str | None,
    action: str,
) -> dict[str, Any] | None:
    """Find one prior operation with the same id and action."""
    if not operation_id:
        return None
    for item in reversed(_operation_history(record)):
        if item.get("id") == operation_id and item.get("action") == action:
            return item
    # Backward-compatible migration path for records written before the
    # bounded operation ledger existed.
    if record:
        legacy_id = (
            record.get("operation_id")
            if action == "pause"
            else record.get("resume_operation_id")
        )
        if legacy_id == operation_id:
            return {
                "id": operation_id,
                "action": action,
                "generation": int(record.get("generation") or 0),
                "result": (
                    _pause_result_from_record(record)
                    if action == "pause"
                    else _resume_result_from_record(record)
                ),
            }
    return None


def _pause_result_from_record(record: dict[str, Any]) -> dict[str, Any]:
    """Build the historical pause result stored in one state record."""
    phase = record.get("phase") or "paused"
    return {
        "camera_id": record.get("camera_id"),
        "camera_entity_id": record.get("camera_entity_id"),
        "paused": phase == "paused" and record.get("active", True),
        "phase": phase,
        "reason": record.get("reason"),
        "operation_id": record.get("operation_id"),
        "switches": list(record.get("switches") or []),
        "skipped": list(record.get("skipped") or []),
        "unavailable": list(record.get("unavailable") or []),
        "failed": list(record.get("failed") or []),
        "camera_toggled": bool(record.get("camera_toggled")),
        "camera_failed": bool(record.get("camera_failed")),
    }


def _resume_result_from_record(record: dict[str, Any]) -> dict[str, Any]:
    """Build the historical resume result stored in one state record."""
    resumed = record.get("phase") == "active" and not record.get("active", True)
    decision = {
        "clear_paused": resumed,
        "keep_paused": not resumed,
        "notification_required": False,
        "reason": record.get("reason"),
        "failed": list(record.get("resume_failed") or []),
        "unavailable": list(record.get("resume_unavailable") or []),
    }
    return _resume_result(
        str(record.get("camera_id") or ""),
        resumed,
        decision,
        False,
        phase="active" if resumed else str(record.get("phase") or "error"),
        operation_id=record.get("resume_operation_id"),
    )


def _upsert_operation(
    history: list[dict[str, Any]],
    *,
    operation_id: str,
    action: str,
    generation: int,
    result: dict[str, Any],
    request_fingerprint: str | None = None,
) -> list[dict[str, Any]]:
    """Append or update one operation while keeping the ledger bounded."""
    clean = [
        deepcopy(item)
        for item in history
        if not (item.get("id") == operation_id and item.get("action") == action)
    ]
    item = {
        "id": operation_id,
        "action": action,
        "generation": generation,
        "result": deepcopy(result),
    }
    if request_fingerprint:
        item["request_fingerprint"] = request_fingerprint
    clean.append(item)
    return clean[-MAX_OPERATION_HISTORY:]


def _request_fingerprint(payload: dict[str, Any]) -> str:
    """Return a stable digest without retaining user-controlled raw payload."""
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _replayed_result(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a stored result for a retry of the current operation."""
    result = deepcopy(entry.get("result") or {})
    result["reason"] = "idempotent_replay"
    result["replayed"] = True
    return result


def _stale_operation_result(
    camera_id: str,
    *,
    action: str,
    operation_id: str,
    current_generation: int,
) -> dict[str, Any]:
    """Reject a delayed request from an older camera generation."""
    common = {
        "camera_id": camera_id,
        "phase": "error",
        "reason": "stale_operation",
        "operation_id": operation_id,
        "current_generation": current_generation,
        "stale": True,
    }
    if action == "pause":
        return {
            **common,
            "paused": False,
            "switches": [],
            "skipped": [],
            "unavailable": [],
            "failed": [],
            "camera_toggled": False,
            "camera_failed": False,
        }
    return {
        **common,
        "resumed": False,
        "automatic": False,
        "fail_safe": True,
        "decision": {
            "clear_paused": False,
            "keep_paused": True,
            "notification_required": False,
            "reason": "stale_operation",
            "failed": [],
            "unavailable": [],
        },
    }


async def _transition(
    storage: FrigatePrivacyStorage,
    camera_id: str,
    phase: str,
    **updates: Any,
) -> dict[str, Any] | None:
    """Persist a state-machine transition through new or legacy storage."""
    transition = getattr(storage, "async_transition_paused", None)
    if transition is not None:
        return await transition(camera_id, phase, **updates)
    current = await storage.async_get_paused(camera_id)
    if not current:
        return None
    current.update(updates)
    current["phase"] = phase
    current["active"] = phase != "active"
    return await storage.async_set_paused(camera_id, current)


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
    return (
        entity_id
        if hass.states.get(entity_id) is not None
        and _is_frigate_entity(hass, entity_id)
        else None
    )


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
        if not _is_frigate_entity(hass, entity_id):
            continue
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
    context: Any | None = None,
    operation_id: str | None = None,
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
                context=context,
                operation_id=_scoped_operation_id(operation_id, ref),
            )
        )
    ok = bool(results) and all(item["paused"] for item in results)
    return {
        "results": results,
        "ok": ok,
        "phase": "paused" if ok else "partial" if results else "error",
    }


async def async_pause_camera(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_ref: str,
    *,
    duration_minutes: int | None = None,
    stream_type: str = "all",
    source: str = "manual",
    schedule_id: str | None = None,
    context: Any | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """Pause one allowlisted camera and persist truthful transition evidence."""
    base = camera_base(camera_ref)
    if base not in _discovered_camera_ids(hass):
        return {
            "camera_id": base,
            "paused": False,
            "phase": "error",
            "reason": "camera_not_discovered",
            "switches": [],
            "skipped": [],
            "failed": [],
            "camera_toggled": False,
            "camera_failed": False,
        }

    async with _camera_lock(storage, base):
        return await _async_pause_camera_locked(
            hass,
            storage,
            base,
            duration_minutes=duration_minutes,
            stream_type=stream_type,
            source=source,
            schedule_id=schedule_id,
            context=context,
            operation_id=operation_id,
        )


async def _async_pause_camera_locked(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    base: str,
    *,
    duration_minutes: int | None,
    stream_type: str,
    source: str,
    schedule_id: str | None,
    context: Any | None,
    operation_id: str | None,
) -> dict[str, Any]:
    """Execute a pause while the camera transition lock is held."""
    record = await _latest_record(storage, base)
    current_generation = int((record or {}).get("generation") or 0)
    request_fingerprint = _request_fingerprint(
        {
            "camera_id": base,
            "duration_minutes": duration_minutes,
            "stream_type": stream_type,
            "source": source,
            "schedule_id": schedule_id,
        }
    )
    prior_operation = _find_operation(record, operation_id, "pause")
    if prior_operation:
        if prior_operation.get("request_fingerprint") not in {
            None,
            request_fingerprint,
        }:
            mismatch = _stale_operation_result(
                base,
                action="pause",
                operation_id=str(operation_id),
                current_generation=current_generation,
            )
            mismatch["reason"] = "operation_payload_mismatch"
            mismatch["stale"] = False
            return mismatch
        if int(prior_operation.get("generation") or 0) == current_generation:
            return _replayed_result(prior_operation)
        return _stale_operation_result(
            base,
            action="pause",
            operation_id=str(operation_id),
            current_generation=current_generation,
        )

    operation_id = operation_id or _new_operation_id("pause", base)
    operation_history = _operation_history(record)
    if not await _reserve_camera_operation(
        storage,
        base,
        "pause",
        operation_id,
        operation_history,
    ):
        return _expired_operation_result(
            base,
            action="pause",
            operation_id=operation_id,
            current_generation=current_generation,
        )

    existing = await storage.async_get_paused(base)
    if existing:
        if (
            source == "schedule"
            and schedule_id
            and (existing.get("phase") or "paused") in {"paused", "partial"}
        ):
            return await _async_extend_schedule_pause_locked(
                hass,
                storage,
                base,
                existing,
                schedule_id=schedule_id,
                context=context,
            )
        existing_phase = existing.get("phase") or "paused"
        return {
            "camera_id": base,
            "camera_entity_id": existing.get("camera_entity_id"),
            "paused": existing_phase == "paused",
            "phase": existing_phase,
            "reason": (
                "idempotent_replay"
                if operation_id and existing.get("operation_id") == operation_id
                else "already_paused"
            ),
            "operation_id": existing.get("operation_id"),
            "switches": list(existing.get("switches") or []),
            "skipped": list(existing.get("skipped") or []),
            "unavailable": list(existing.get("unavailable") or []),
            "failed": list(existing.get("failed") or []),
            "camera_toggled": bool(existing.get("camera_toggled")),
            "camera_failed": bool(existing.get("camera_failed")),
        }
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
    planned_switches: list[str] = []
    preexisting_off: list[str] = []
    unavailable: list[str] = []
    camera_toggled = False
    camera_failed = False

    for item in switches:
        entity_id = item["entity_id"]
        state = hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE_STATES:
            unavailable.append(entity_id)
        elif state.state == "off":
            preexisting_off.append(entity_id)
        else:
            planned_switches.append(entity_id)

    camera_planned = bool(
        stream_type == "all"
        and cam_entity
        and (camera_state := hass.states.get(cam_entity)) is not None
        and camera_state.state not in {*UNAVAILABLE_STATES, "off"}
    )
    if stream_type == "all" and cam_entity:
        camera_state = hass.states.get(cam_entity)
        if camera_state is None or camera_state.state in UNAVAILABLE_STATES:
            unavailable.append(cam_entity)

    target_outcomes: dict[str, str] = {
        **{entity_id: "missing" for entity_id in missing},
        **{entity_id: "unavailable" for entity_id in unavailable},
        **{entity_id: "preexisting_off" for entity_id in preexisting_off},
        **{entity_id: "pending" for entity_id in planned_switches},
    }
    if camera_planned and cam_entity:
        target_outcomes[cam_entity] = "pending"

    now = datetime.now(timezone.utc)
    ends_at = (
        now + timedelta(minutes=duration_minutes)
        if duration_minutes is not None
        else None
    )
    generation = current_generation + 1
    operation_history = _upsert_operation(
        operation_history,
        operation_id=operation_id,
        action="pause",
        generation=generation,
        result={
            "camera_id": base,
            "camera_entity_id": cam_entity,
            "paused": False,
            "phase": "pausing",
            "reason": None,
            "operation_id": operation_id,
            "switches": [],
            "skipped": skipped,
            "unavailable": unavailable,
            "failed": [],
            "camera_toggled": False,
            "camera_failed": False,
        },
        request_fingerprint=request_fingerprint,
    )
    await storage.async_set_paused(
        base,
        {
            "camera_entity_id": cam_entity,
            "name": _camera_name(hass, cam_entity, base),
            "phase": "pausing",
            "desired_state": "paused",
            "operation_id": operation_id,
            "generation": generation,
            "operation_history": operation_history,
            "request_user_id": getattr(context, "user_id", None),
            "stream_type": stream_type,
            "source": source,
            "schedule_id": schedule_id,
            "planned_switches": planned_switches,
            "switches": [],
            "preexisting_off": preexisting_off,
            "skipped": skipped,
            "unavailable": unavailable,
            "failed": [],
            "camera_planned": camera_planned,
            "camera_toggled": False,
            "camera_failed": False,
            "target_outcomes": target_outcomes,
            "started_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "ends_at": ends_at.isoformat() if ends_at else None,
            "resume_blocked": False,
        },
    )

    for entity_id in planned_switches:
        try:
            await hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": entity_id},
                blocking=True,
                context=context,
            )
        except Exception as err:  # noqa: BLE001 - surface in result
            _LOGGER.warning("Failed to pause a managed target (%s)", type(err).__name__)
            failed.append(entity_id)
            target_outcomes[entity_id] = "service_failed"
        else:
            state = hass.states.get(entity_id)
            if state is not None and state.state == "off":
                toggled.append(entity_id)
                target_outcomes[entity_id] = "paused"
            else:
                failed.append(entity_id)
                target_outcomes[entity_id] = "readback_failed"
        await _transition(
            storage,
            base,
            "pausing",
            switches=list(toggled),
            failed=list(failed),
            target_outcomes=dict(target_outcomes),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    if camera_planned and cam_entity:
        try:
            await hass.services.async_call(
                "camera",
                "turn_off",
                {"entity_id": cam_entity},
                blocking=True,
                context=context,
            )
            camera_state = hass.states.get(cam_entity)
            camera_toggled = bool(camera_state and camera_state.state == "off")
            camera_failed = not camera_toggled
            if camera_toggled:
                target_outcomes[cam_entity] = "paused"
            else:
                target_outcomes[cam_entity] = "readback_failed"
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to stop a managed camera (%s)", type(err).__name__)
            camera_failed = True
            target_outcomes[cam_entity] = "service_failed"
        await _transition(
            storage,
            base,
            "pausing",
            switches=list(toggled),
            failed=list(failed),
            camera_toggled=camera_toggled,
            camera_failed=camera_failed,
            target_outcomes=dict(target_outcomes),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    phase = "partial" if failed or unavailable or camera_failed else "paused"
    paused = phase == "paused"
    observed_at = datetime.now(timezone.utc).isoformat()
    observed_targets = list(
        dict.fromkeys(
            [
                *planned_switches,
                *preexisting_off,
                *unavailable,
                *([cam_entity] if cam_entity else []),
            ]
        )
    )
    result = {
        "camera_id": base,
        "camera_entity_id": cam_entity,
        "paused": paused,
        "phase": phase,
        "reason": "pause_incomplete" if phase == "partial" else None,
        "operation_id": operation_id,
        "switches": toggled,
        "skipped": skipped,
        "unavailable": unavailable,
        "failed": failed,
        "camera_toggled": camera_toggled,
        "camera_failed": camera_failed,
    }
    operation_history = _upsert_operation(
        operation_history,
        operation_id=operation_id,
        action="pause",
        generation=generation,
        result=result,
        request_fingerprint=request_fingerprint,
    )
    await _transition(
        storage,
        base,
        phase,
        switches=toggled,
        unavailable=unavailable,
        failed=failed,
        camera_toggled=camera_toggled,
        camera_failed=camera_failed,
        target_outcomes=target_outcomes,
        reason="pause_incomplete" if phase == "partial" else None,
        observed_at=observed_at,
        updated_at=observed_at,
        last_verified_state=phase,
        last_verified_actual_state=_actual_state_snapshot(hass, observed_targets),
        operation_history=operation_history,
    )
    hass.bus.async_fire(EVENT_STATE_CHANGED, {"camera_id": base})
    return result


async def _async_extend_schedule_pause_locked(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    base: str,
    existing: dict[str, Any],
    *,
    schedule_id: str,
    context: Any | None,
) -> dict[str, Any]:
    """Add schedule coverage to an existing pause without a privacy gap."""
    coverage = sorted(
        {
            *(existing.get("active_schedule_ids") or []),
            schedule_id,
        }
    )
    existing_switches = list(existing.get("switches") or [])
    preexisting_off = list(existing.get("preexisting_off") or [])
    unavailable = list(existing.get("unavailable") or [])
    failed: list[str] = []
    outcomes = dict(existing.get("target_outcomes") or {})
    extension_planned: list[str] = []

    for item in _switches_for_base(hass, base, ALL_SUFFIXES):
        entity_id = item["entity_id"]
        if entity_id in existing_switches or entity_id in preexisting_off:
            continue
        state = hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE_STATES:
            unavailable.append(entity_id)
            outcomes[entity_id] = "unavailable"
        elif state.state == "off":
            preexisting_off.append(entity_id)
            outcomes[entity_id] = "preexisting_off"
        else:
            extension_planned.append(entity_id)
            outcomes[entity_id] = "pending"

    cam_entity = existing.get("camera_entity_id") or camera_entity_id(hass, base)
    camera_toggled = bool(existing.get("camera_toggled"))
    camera_planned = bool(
        not camera_toggled
        and cam_entity
        and _camera_is_enabled(hass, cam_entity)
    )
    if camera_planned and cam_entity:
        outcomes[cam_entity] = "pending"

    source = existing.get("source") or "manual"
    await _transition(
        storage,
        base,
        "pausing",
        source=source,
        schedule_id=coverage[0],
        active_schedule_ids=coverage,
        extension=True,
        extension_base_switches=existing_switches,
        extension_planned_switches=extension_planned,
        camera_planned=camera_planned,
        preexisting_off=list(dict.fromkeys(preexisting_off)),
        unavailable=list(dict.fromkeys(unavailable)),
        target_outcomes=outcomes,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    toggled = list(existing_switches)
    for entity_id in extension_planned:
        try:
            await hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": entity_id},
                blocking=True,
                context=context,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to extend a managed privacy target (%s)",
                type(err).__name__,
            )
            failed.append(entity_id)
            outcomes[entity_id] = "service_failed"
        else:
            state = hass.states.get(entity_id)
            if state is not None and state.state == "off":
                toggled.append(entity_id)
                outcomes[entity_id] = "paused"
            else:
                failed.append(entity_id)
                outcomes[entity_id] = "readback_failed"
        await _transition(
            storage,
            base,
            "pausing",
            switches=list(dict.fromkeys(toggled)),
            failed=list(failed),
            target_outcomes=outcomes,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    if camera_planned and cam_entity:
        try:
            await hass.services.async_call(
                "camera",
                "turn_off",
                {"entity_id": cam_entity},
                blocking=True,
                context=context,
            )
            camera_toggled = bool(
                (state := hass.states.get(cam_entity)) and state.state == "off"
            )
            outcomes[cam_entity] = (
                "paused" if camera_toggled else "readback_failed"
            )
            if not camera_toggled:
                failed.append(cam_entity)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to extend managed camera privacy (%s)",
                type(err).__name__,
            )
            failed.append(cam_entity)
            outcomes[cam_entity] = "service_failed"

    phase = "partial" if failed or unavailable else "paused"
    observed_at = datetime.now(timezone.utc).isoformat()
    targets = [
        *list(dict.fromkeys(toggled)),
        *([cam_entity] if cam_entity else []),
    ]
    await _transition(
        storage,
        base,
        phase,
        switches=list(dict.fromkeys(toggled)),
        camera_toggled=camera_toggled,
        failed=list(dict.fromkeys(failed)),
        unavailable=list(dict.fromkeys(unavailable)),
        target_outcomes=outcomes,
        reason="pause_incomplete" if phase == "partial" else None,
        last_verified_actual_state=_actual_state_snapshot(hass, targets),
        observed_at=observed_at,
        updated_at=observed_at,
    )
    hass.bus.async_fire(EVENT_STATE_CHANGED, {"camera_id": base})
    return {
        "camera_id": base,
        "camera_entity_id": cam_entity,
        "paused": phase == "paused",
        "phase": phase,
        "reason": "pause_incomplete" if phase == "partial" else None,
        "operation_id": existing.get("operation_id"),
        "switches": list(dict.fromkeys(toggled)),
        "skipped": list(existing.get("skipped") or []),
        "unavailable": list(dict.fromkeys(unavailable)),
        "failed": list(dict.fromkeys(failed)),
        "camera_toggled": camera_toggled,
        "camera_failed": cam_entity in failed if cam_entity else False,
    }


async def async_resume_cameras(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_refs: list[str] | None,
    *,
    authority: ResumeAuthority = ResumeAuthority.ADMIN,
    reason: str = "admin_request",
    context: Any | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """Resume selected or all paused cameras."""
    paused_all = await storage.async_get_paused(None)
    refs = camera_refs or list((paused_all or {}).keys())
    if not refs:
        refs = [item["camera_id"] for item in discover_frigate_cameras(hass)]
    results = []
    for ref in refs:
        results.append(
            await async_resume_camera(
                hass,
                storage,
                ref,
                authority=authority,
                reason=reason,
                context=context,
                operation_id=_scoped_operation_id(operation_id, ref),
            )
        )
    ok = all(item["resumed"] for item in results)
    return {
        "results": results,
        "ok": ok,
        "phase": "active" if ok else "error",
    }


async def async_resume_camera(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_ref: str,
    *,
    authority: ResumeAuthority = ResumeAuthority.ADMIN,
    reason: str = "admin_request",
    context: Any | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    """Resume one camera once, with privacy-first fail-safe semantics."""
    base = camera_base(camera_ref)
    async with _camera_lock(storage, base):
        return await _async_resume_camera_locked(
            hass,
            storage,
            base,
            authority=authority,
            reason=reason,
            context=context,
            operation_id=operation_id,
        )


async def _async_resume_camera_locked(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    base: str,
    *,
    authority: ResumeAuthority,
    reason: str,
    context: Any | None,
    operation_id: str | None,
) -> dict[str, Any]:
    """Execute a resume while the camera transition lock is held."""
    if not isinstance(authority, ResumeAuthority):
        raise ValueError("resume authority must be explicit")
    automatic = authority is not ResumeAuthority.ADMIN
    record = await _latest_record(storage, base)
    current_generation = int((record or {}).get("generation") or 0)
    recovery_continuation = bool(
        authority is ResumeAuthority.RECOVERY
        and record
        and (record.get("phase") or "paused") == "resuming"
        and operation_id
        and record.get("resume_operation_id") == operation_id
    )
    prior_operation = _find_operation(record, operation_id, "resume")
    if prior_operation and not recovery_continuation:
        if int(prior_operation.get("generation") or 0) == current_generation:
            return _replayed_result(prior_operation)
        return _stale_operation_result(
            base,
            action="resume",
            operation_id=str(operation_id),
            current_generation=current_generation,
        )

    operation_id = operation_id or _new_operation_id("resume", base)
    operation_history = _operation_history(record)
    if not recovery_continuation and not await _reserve_camera_operation(
        storage,
        base,
        "resume",
        operation_id,
        operation_history,
    ):
        return _expired_operation_result(
            base,
            action="resume",
            operation_id=operation_id,
            current_generation=current_generation,
        )

    paused = await storage.async_get_paused(base)
    if not paused:
        return {
            "camera_id": base,
            "resumed": True,
            "phase": "active",
            "nothing_to_resume": True,
            "fail_safe": False,
        }
    if (paused.get("phase") or "paused") in {
        "pausing",
        "resuming",
    } and not _recovery_inputs_ready(hass, paused):
        return {
            "camera_id": base,
            "resumed": False,
            "phase": "recovering",
            "reason": "recovery_pending",
            "automatic": automatic,
            "fail_safe": True,
            "decision": {
                "clear_paused": False,
                "keep_paused": True,
                "notification_required": False,
                "reason": "recovery_pending",
                "failed": [],
                "unavailable": [],
            },
        }

    expected_raw = paused.get("switches") or []
    cam_entity = paused.get("camera_entity_id") or camera_entity_id(hass, base)
    if not _persisted_targets_are_valid(
        hass,
        base,
        expected_raw,
        cam_entity,
        bool(paused.get("camera_toggled")),
    ):
        decision = {
            "clear_paused": False,
            "keep_paused": True,
            "notification_required": False,
            "reason": "invalid_persisted_targets",
            "failed": [],
            "unavailable": [],
        }
        await storage.async_mark_resume_blocked(
            base,
            reason=decision["reason"],
            failed=[],
            unavailable=[],
        )
        hass.bus.async_fire(EVENT_STATE_CHANGED, {"camera_id": base})
        return _resume_result(base, False, decision, automatic, phase="error")
    generation = (
        current_generation if recovery_continuation else current_generation + 1
    )
    attempt_count = int(paused.get("resume_attempt_count") or 0) + 1
    attempt_at = datetime.now(timezone.utc).isoformat()
    operation_history = _upsert_operation(
        operation_history,
        operation_id=operation_id,
        action="resume",
        generation=generation,
        result=_resume_result(
            base,
            False,
            {
                "clear_paused": False,
                "keep_paused": True,
                "notification_required": False,
                "reason": "resume_in_progress",
                "failed": [],
                "unavailable": [],
            },
            automatic,
            phase="resuming",
            operation_id=operation_id,
        ),
    )
    await _transition(
        storage,
        base,
        "resuming",
        desired_state="active",
        generation=generation,
        operation_history=operation_history,
        resume_operation_id=operation_id,
        resume_request_user_id=getattr(context, "user_id", None),
        resume_authority=authority.value,
        resume_reason=reason,
        resume_started_at=attempt_at,
        resume_attempt_count=attempt_count,
        last_attempt_at=attempt_at,
        last_attempt_operation_id=operation_id,
        resume_blocked=False,
        reason=None,
    )

    expected = list(expected_raw)
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
        result = _resume_result(
            base,
            False,
            preflight,
            automatic,
            phase="error",
            operation_id=operation_id,
        )
        operation_history = _upsert_operation(
            operation_history,
            operation_id=operation_id,
            action="resume",
            generation=generation,
            result=result,
        )
        await _hold_fail_safe(
            hass,
            storage,
            base,
            paused,
            preflight,
            evidence={"operation_history": operation_history},
        )
        return result

    failed: list[str] = []
    camera_turned_on = False
    resume_completed: list[str] = []
    reenabled_switches: list[str] = []
    camera_reenabled = False
    try:
        if paused.get("camera_toggled") and cam_entity:
            if _camera_is_enabled(hass, cam_entity):
                camera_reenabled = True
                resume_completed.append(cam_entity)
            else:
                await hass.services.async_call(
                    "camera",
                    "turn_on",
                    {"entity_id": cam_entity},
                    blocking=True,
                    context=context,
                )
                camera_turned_on = _camera_is_enabled(hass, cam_entity)
                camera_reenabled = camera_turned_on
                if not camera_turned_on:
                    failed.append(cam_entity)
                else:
                    resume_completed.append(cam_entity)
                    await _transition(
                        storage,
                        base,
                        "resuming",
                        resume_completed=list(resume_completed),
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
        for entity_id in expected:
            if failed:
                break
            if hass.states.get(entity_id).state == "on":
                resume_completed.append(entity_id)
                reenabled_switches.append(entity_id)
                continue
            await hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": entity_id},
                blocking=True,
                context=context,
            )
            state = hass.states.get(entity_id)
            if state is not None and state.state == "on":
                reenabled_switches.append(entity_id)
                resume_completed.append(entity_id)
                await _transition(
                    storage,
                    base,
                    "resuming",
                    resume_completed=list(resume_completed),
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
            else:
                failed.append(entity_id)
    except asyncio.CancelledError:
        # A service call can have completed before the caller observes task
        # cancellation. Re-read every exact persisted target and restore the
        # privacy/off state in a shielded task before propagating cancellation.
        restore_switches = [
            target
            for target in expected
            if (state := hass.states.get(target)) is not None
            and state.state == "on"
        ]
        restore_camera = (
            cam_entity
            if paused.get("camera_toggled")
            and cam_entity
            and _camera_is_enabled(hass, cam_entity)
            else None
        )
        restored = await _await_cleanup(
            _restore_pause_after_failed_resume(
                hass,
                restore_switches,
                restore_camera,
                context=context,
            )
        )
        cancellation_decision = {
            "clear_paused": False,
            "keep_paused": True,
            "notification_required": True,
            "reason": "resume_cancelled",
            "failed": list(restored["failed"]),
            "unavailable": [],
        }
        cancellation_result = _resume_result(
            base,
            False,
            cancellation_decision,
            automatic,
            phase="error",
            operation_id=operation_id,
        )
        cancellation_history = _upsert_operation(
            operation_history,
            operation_id=operation_id,
            action="resume",
            generation=generation,
            result=cancellation_result,
        )
        await _await_cleanup(
            _hold_fail_safe(
                hass,
                storage,
                base,
                paused,
                cancellation_decision,
                evidence={
                    "resume_target_outcomes": restored["outcomes"],
                    "fail_safe_failed": restored["failed"],
                    "last_verified_actual_state": restored["actual"],
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "operation_history": cancellation_history,
                },
            )
        )
        raise
    except Exception as err:  # noqa: BLE001 - fail-safe branch
        failed.append(entity_id if "entity_id" in locals() else cam_entity or base)
        _LOGGER.warning("Resume target failed (%s)", type(err).__name__)

    decision = decide_resume_exit(
        attempted=expected,
        unavailable=[],
        failed=failed,
    )
    if decision["clear_paused"]:
        targets = [
            *([cam_entity] if paused.get("camera_toggled") and cam_entity else []),
            *expected,
        ]
        observed_at = datetime.now(timezone.utc).isoformat()
        actual = _actual_state_snapshot(hass, targets)
        result = _resume_result(
            base,
            True,
            decision,
            automatic,
            phase="active",
            operation_id=operation_id,
        )
        operation_history = _upsert_operation(
            operation_history,
            operation_id=operation_id,
            action="resume",
            generation=generation,
            result=result,
        )
        try:
            await storage.async_mark_active(
                base,
                resume_operation_id=operation_id,
                resume_completed=list(resume_completed),
                resume_target_outcomes={
                    entity_id: "active" for entity_id in targets
                },
                last_verified_actual_state=actual,
                observed_at=observed_at,
                updated_at=observed_at,
                resume_blocked=False,
                reason=None,
                operation_history=operation_history,
            )
        except Exception as err:  # noqa: BLE001 - restore privacy on uncertainty
            _LOGGER.error(
                "Could not persist terminal active state (%s)",
                type(err).__name__,
            )
            restored = await _restore_pause_after_failed_resume(
                hass,
                reenabled_switches,
                cam_entity if camera_reenabled else None,
                context=context,
            )
            persistence_decision = {
                "clear_paused": False,
                "keep_paused": True,
                "notification_required": True,
                "reason": "state_persistence_failed",
                "failed": list(restored["failed"]),
                "unavailable": [],
            }
            await _hold_fail_safe(
                hass,
                storage,
                base,
                paused,
                persistence_decision,
                evidence={
                    "resume_target_outcomes": restored["outcomes"],
                    "last_verified_actual_state": restored["actual"],
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            result = _resume_result(
                base,
                False,
                persistence_decision,
                automatic,
                phase="error",
                operation_id=operation_id,
            )
            failed_history = _upsert_operation(
                operation_history,
                operation_id=operation_id,
                action="resume",
                generation=generation,
                result=result,
            )
            await _transition(
                storage,
                base,
                "error",
                operation_history=failed_history,
            )
            return result
        hass.bus.async_fire(EVENT_STATE_CHANGED, {"camera_id": base})
        return result

    # Explicit fail-safe: if a resume call fails after any successful turn_on,
    # immediately try to restore the paused/off state, keep storage active, and
    # notify. We never clear paused state on uncertainty.
    restored = await _restore_pause_after_failed_resume(
        hass,
        reenabled_switches,
        cam_entity if camera_reenabled else None,
        context=context,
    )
    result = _resume_result(
        base,
        False,
        decision,
        automatic,
        phase="error",
        operation_id=operation_id,
    )
    operation_history = _upsert_operation(
        operation_history,
        operation_id=operation_id,
        action="resume",
        generation=generation,
        result=result,
    )
    await _hold_fail_safe(
        hass,
        storage,
        base,
        paused,
        decision,
        evidence={
            "resume_target_outcomes": restored["outcomes"],
            "fail_safe_failed": restored["failed"],
            "last_verified_actual_state": restored["actual"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "operation_history": operation_history,
        },
    )
    return result


async def async_recover_transitions(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
) -> dict[str, list[str]]:
    """Reconcile persisted nonterminal transitions after startup."""
    paused_all = await storage.async_get_paused(None) or {}
    recovered: list[str] = []
    held: list[str] = []
    pending: list[str] = []
    for camera_id, state in paused_all.items():
        phase = state.get("phase") or "paused"
        if phase in {"pausing", "resuming"} and not _recovery_inputs_ready(
            hass, state
        ):
            # Frigate can finish entity registration after this integration
            # loads. Never rewrite exact-target evidence merely because the
            # dependency is not visible yet; a later owned scheduler tick
            # will retry recovery when the entities arrive.
            pending.append(camera_id)
            continue
        if phase == "resuming":
            result = await async_resume_camera(
                hass,
                storage,
                camera_id,
                authority=ResumeAuthority.RECOVERY,
                reason="restart_recovery",
                operation_id=state.get("resume_operation_id"),
            )
            if result.get("resumed"):
                recovered.append(camera_id)
            else:
                held.append(camera_id)
        elif phase == "pausing":
            planned_switches = list(
                state.get("extension_planned_switches")
                if state.get("extension")
                else state.get("planned_switches")
                or []
            )
            base_switches = list(
                state.get("extension_base_switches") or []
                if state.get("extension")
                else []
            )
            recovered_switches = list(dict.fromkeys([
                *base_switches,
                *[
                entity_id
                for entity_id in planned_switches
                if (current := hass.states.get(entity_id)) is not None
                and current.state == "off"
                ],
            ]))
            camera_entity = state.get("camera_entity_id")
            camera_toggled = bool(
                state.get("camera_toggled")
                or (
                    state.get("camera_planned")
                    and camera_entity
                    and (current := hass.states.get(camera_entity)) is not None
                    and current.state == "off"
                )
            )
            await _transition(
                storage,
                camera_id,
                "partial",
                reason="restart_during_pause",
                switches=recovered_switches,
                camera_toggled=camera_toggled,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            held.append(camera_id)
    return {"recovered": recovered, "held": held, "pending": pending}


def _recovery_inputs_ready(
    hass: HomeAssistant, state: dict[str, Any]
) -> bool:
    """Return whether exact persisted targets are registered and observable."""
    phase = state.get("phase") or "paused"
    if phase == "resuming":
        targets = list(state.get("switches") or [])
        if state.get("camera_toggled") and state.get("camera_entity_id"):
            targets.append(state["camera_entity_id"])
    else:
        targets = list(
            state.get("extension_planned_switches")
            if state.get("extension")
            else state.get("planned_switches")
            or []
        )
        if state.get("extension"):
            targets.extend(state.get("extension_base_switches") or [])
        if state.get("camera_planned") and state.get("camera_entity_id"):
            targets.append(state["camera_entity_id"])
    return all(
        hass.states.get(entity_id) is not None
        and _is_frigate_entity(hass, entity_id)
        for entity_id in dict.fromkeys(targets)
    )


async def async_finalize_recovery_pending(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_ids: list[str],
) -> list[str]:
    """End startup grace without losing exact evidence for missing targets."""
    finalized: list[str] = []
    for camera_id in camera_ids:
        state = await storage.async_get_paused(camera_id)
        if not state or (state.get("phase") or "paused") not in {
            "pausing",
            "resuming",
        }:
            continue
        phase = state.get("phase") or "paused"
        if phase == "resuming":
            planned = list(state.get("switches") or [])
            camera_expected = bool(state.get("camera_toggled"))
        else:
            planned = list(
                state.get("extension_planned_switches")
                if state.get("extension")
                else state.get("planned_switches")
                or []
            )
            if state.get("extension"):
                planned = [
                    *(state.get("extension_base_switches") or []),
                    *planned,
                ]
            camera_expected = bool(state.get("camera_planned"))

        camera_entity = state.get("camera_entity_id")
        targets = list(dict.fromkeys(planned))
        if camera_expected and camera_entity:
            targets.append(camera_entity)
        missing = [
            entity_id
            for entity_id in targets
            if hass.states.get(entity_id) is None
            or not _is_frigate_entity(hass, entity_id)
        ]
        outcomes = dict(state.get("target_outcomes") or {})
        outcomes.update({entity_id: "missing_after_startup" for entity_id in missing})
        known_paused = list(state.get("switches") or [])
        if phase == "pausing":
            known_paused = list(
                dict.fromkeys(
                    [
                        *known_paused,
                        *[
                            entity_id
                            for entity_id in planned
                            if (current := hass.states.get(entity_id)) is not None
                            and current.state == "off"
                            and _is_frigate_entity(hass, entity_id)
                        ],
                    ]
                )
            )
        camera_toggled = bool(
            state.get("camera_toggled")
            or (
                phase == "pausing"
                and camera_expected
                and camera_entity
                and (current := hass.states.get(camera_entity)) is not None
                and current.state == "off"
                and _is_frigate_entity(hass, camera_entity)
            )
        )
        await _transition(
            storage,
            camera_id,
            "error",
            reason="recovery_targets_missing",
            recovery_missing_targets=missing,
            switches=known_paused,
            camera_toggled=camera_toggled,
            target_outcomes=outcomes,
            resume_blocked=True,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        finalized.append(camera_id)
    return finalized


def _switches_for_base(
    hass: HomeAssistant, base: str, suffixes: tuple[str, ...]
) -> list[dict[str, Any]]:
    switches = []
    for suffix in suffixes:
        entity_id = f"switch.{base}{suffix}"
        state = hass.states.get(entity_id)
        if state is None or not _is_frigate_entity(hass, entity_id):
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


def _actual_state_snapshot(
    hass: HomeAssistant, entity_ids: list[str]
) -> dict[str, str | None]:
    """Return a redaction-safe current state snapshot for exact targets."""
    return {
        entity_id: (state.state if (state := hass.states.get(entity_id)) else None)
        for entity_id in entity_ids
    }


def _persisted_targets_are_valid(
    hass: HomeAssistant,
    camera_id: str,
    switches: Any,
    camera_entity: Any,
    camera_toggled: bool,
) -> bool:
    """Fail closed when persisted control evidence contains unrelated targets."""
    if not isinstance(switches, list) or not all(
        isinstance(entity_id, str) for entity_id in switches
    ):
        return False
    allowed = {f"switch.{camera_id}{suffix}" for suffix in ALL_SUFFIXES}
    if len(set(switches)) != len(switches):
        return False
    if any(
        entity_id not in allowed or not _is_frigate_entity(hass, entity_id)
        for entity_id in switches
    ):
        return False
    if not camera_toggled:
        return camera_entity is None or camera_entity == f"camera.{camera_id}"
    return bool(
        camera_entity == f"camera.{camera_id}"
        and _is_frigate_entity(hass, camera_entity)
    )


def _camera_is_enabled(hass: HomeAssistant, entity_id: str) -> bool:
    """Return whether a camera is enabled across HA camera state variants."""
    state = hass.states.get(entity_id)
    return bool(state and state.state not in {*UNAVAILABLE_STATES, "off"})


async def _restore_pause_after_failed_resume(
    hass: HomeAssistant,
    switches: list[str],
    camera_entity: str | None,
    *,
    context: Any | None,
) -> dict[str, Any]:
    failed: list[str] = []
    outcomes: dict[str, str] = {}
    for entity_id in switches:
        try:
            await hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": entity_id},
                blocking=True,
                context=context,
            )
            state = hass.states.get(entity_id)
            if state is not None and state.state == "off":
                outcomes[entity_id] = "repaused"
            else:
                outcomes[entity_id] = "re_pause_readback_failed"
                failed.append(entity_id)
        except asyncio.CancelledError:
            outcomes[entity_id] = "re_pause_cancelled"
            failed.append(entity_id)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Fail-safe re-pause failed (%s)", type(err).__name__)
            outcomes[entity_id] = "re_pause_service_failed"
            failed.append(entity_id)
    if camera_entity:
        try:
            await hass.services.async_call(
                "camera",
                "turn_off",
                {"entity_id": camera_entity},
                blocking=True,
                context=context,
            )
            state = hass.states.get(camera_entity)
            if state is not None and state.state == "off":
                outcomes[camera_entity] = "repaused"
            else:
                outcomes[camera_entity] = "re_pause_readback_failed"
                failed.append(camera_entity)
        except asyncio.CancelledError:
            outcomes[camera_entity] = "re_pause_cancelled"
            failed.append(camera_entity)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Fail-safe camera stream re-pause failed (%s)",
                type(err).__name__,
            )
            outcomes[camera_entity] = "re_pause_service_failed"
            failed.append(camera_entity)
    targets = [*switches, *([camera_entity] if camera_entity else [])]
    return {
        "failed": list(dict.fromkeys(failed)),
        "outcomes": outcomes,
        "actual": _actual_state_snapshot(hass, targets),
    }


async def _await_cleanup(coro: Any) -> Any:
    """Finish a fail-safe cleanup despite repeated caller cancellation."""
    task = asyncio.create_task(coro)
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()
            continue


async def _hold_fail_safe(
    hass: HomeAssistant,
    storage: FrigatePrivacyStorage,
    camera_id: str,
    paused: dict[str, Any],
    decision: dict[str, Any],
    *,
    evidence: dict[str, Any] | None = None,
) -> None:
    try:
        await storage.async_mark_resume_blocked(
            camera_id,
            reason=str(decision["reason"]),
            failed=decision["failed"],
            unavailable=decision["unavailable"],
        )
        if evidence:
            await _transition(storage, camera_id, "error", **evidence)
    except Exception as err:  # noqa: BLE001 - persisted resuming intent remains
        _LOGGER.error("Could not persist fail-safe evidence (%s)", type(err).__name__)
    await _notify_resume_failed(hass, paused, decision)
    hass.bus.async_fire(EVENT_STATE_CHANGED, {"camera_id": camera_id})


async def _notify_resume_failed(
    hass: HomeAssistant, paused: dict[str, Any], decision: dict[str, Any]
) -> None:
    camera_id = str(paused.get("camera_id") or "unknown")
    notification_ref = hashlib.sha256(
        f"resume-failed\0{camera_id}".encode()
    ).hexdigest()[:16]
    message = (
        "Frigate Privacy could not safely end a privacy window. The affected "
        "camera remains marked private because resume was uncertain. An "
        "administrator can review exact target evidence in the Frigate Privacy "
        "card and resume when safe."
    )
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": f"{DOMAIN}_resume_failed_{notification_ref}",
                "title": "Frigate Privacy resume blocked",
                "message": message,
            },
            blocking=False,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not create fail-safe notification (%s)", type(err).__name__
        )


def _resume_result(
    camera_id: str,
    resumed: bool,
    decision: dict[str, Any],
    automatic: bool,
    *,
    phase: str,
    operation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "camera_id": camera_id,
        "resumed": resumed,
        "phase": phase,
        "operation_id": operation_id,
        "automatic": automatic,
        "fail_safe": not resumed,
        "decision": decision,
    }
