"""WebSocket API for Frigate Privacy."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import (
    DATA_SCHEDULER,
    DATA_RECOVERY_READY,
    DATA_STORAGE,
    DOMAIN,
    EVENT_STATE_CHANGED,
    STREAM_TYPES,
)
from .control import (
    async_pause_cameras,
    async_resume_cameras,
    discover_frigate_cameras,
)
from .replay import ReplayFilterSaturatedError
from .storage import (
    FrigatePrivacyStorage,
    ReplayIntegrityError,
    StorageWriteError,
)

_LOGGER = logging.getLogger(__name__)

_CAMERA_REF = vol.All(str, vol.Length(min=1, max=255))
_CAMERA_REFS = vol.All([_CAMERA_REF], vol.Length(min=1, max=64))
_CAMERA_FIELD = vol.Any(_CAMERA_REF, _CAMERA_REFS)
_OPERATION_ID = vol.All(str, vol.Length(min=1, max=128))
_SCHEDULE_ID = vol.All(str, vol.Length(min=1, max=128))
_SCHEDULES = vol.All([dict], vol.Length(max=256))


def _send_recovery_pending(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> bool:
    """Reject mutations while exact persisted targets await reconciliation."""
    if hass.data.get(DOMAIN, {}).get(DATA_RECOVERY_READY, False):
        return False
    connection.send_error(
        msg["id"],
        "recovery_pending",
        "Frigate Privacy is still reconciling persisted privacy state",
    )
    return True


def _storage(hass: HomeAssistant) -> FrigatePrivacyStorage:
    return hass.data[DOMAIN][DATA_STORAGE]


# Camera topology, privacy schedules, and paused-state evidence reveal household
# routines. Keep every command admin-only rather than bypassing HA entity-level
# visibility through a custom aggregate endpoint.
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list_cameras"})
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_list_cameras(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return Frigate cameras discovered from switch.<cam>_detect/_recordings."""
    connection.send_result(msg["id"], {"cameras": discover_frigate_cameras(hass)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_schedules"})
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_get_schedules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return persisted privacy schedules."""
    connection.send_result(msg["id"], {"schedules": await _storage(hass).async_get_schedules()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_schedule",
        vol.Optional("action", default="upsert"): vol.In(
            ["upsert", "delete", "replace_all", "clear"]
        ),
        vol.Optional("schedule"): dict,
        vol.Optional("schedule_id"): _SCHEDULE_ID,
        vol.Optional("schedules"): _SCHEDULES,
        vol.Optional("operation_id"): _OPERATION_ID,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_set_schedule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create, update, delete, replace, or clear schedules."""
    if _send_recovery_pending(hass, connection, msg):
        return
    storage = _storage(hass)
    action = msg["action"]
    try:
        result = await storage.async_apply_schedule_operation(
            operation_id=msg.get("operation_id"),
            action=action,
            schedule=msg.get("schedule"),
            schedule_id=msg.get("schedule_id"),
            schedules=msg.get("schedules"),
            request_user_id=getattr(connection.context(msg), "user_id", None),
        )
    except ReplayFilterSaturatedError:
        connection.send_error(
            msg["id"],
            "replay_saturated",
            "Replay protection is full; no schedule change was applied",
        )
        return
    except ReplayIntegrityError:
        connection.send_error(
            msg["id"],
            "replay_integrity",
            "Replay protection could not be verified; schedule changes are blocked",
        )
        return
    except StorageWriteError:
        connection.send_error(
            msg["id"],
            "storage_failed",
            "The schedule was not durably saved",
        )
        return
    except ValueError:
        connection.send_error(
            msg["id"], "invalid_payload", "Invalid schedule payload"
        )
        return
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("set_schedule failed (%s)", type(err).__name__)
        connection.send_error(
            msg["id"], "set_schedule_failed", "Could not update the schedule"
        )
        return

    hass.bus.async_fire(EVENT_STATE_CHANGED, {"schedules": True})
    if scheduler := hass.data[DOMAIN].get(DATA_SCHEDULER):
        scheduler.async_request_tick()
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/pause_camera",
        vol.Optional("camera"): _CAMERA_FIELD,
        vol.Optional("camera_entity_id"): _CAMERA_FIELD,
        vol.Optional("cameras"): _CAMERA_REFS,
        vol.Optional("duration_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
        vol.Optional("stream_type", default="all"): vol.In(STREAM_TYPES),
        vol.Optional("operation_id"): _OPERATION_ID,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_pause_camera(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Pause one or more Frigate cameras."""
    if _send_recovery_pending(hass, connection, msg):
        return
    try:
        result = await async_pause_cameras(
            hass,
            _storage(hass),
            _camera_refs(msg),
            duration_minutes=msg.get("duration_minutes"),
            stream_type=msg["stream_type"],
            source="manual",
            context=connection.context(msg),
            operation_id=msg.get("operation_id"),
        )
    except ReplayFilterSaturatedError:
        connection.send_error(
            msg["id"],
            "replay_saturated",
            "Replay protection is full; no camera change was applied",
        )
        return
    except ReplayIntegrityError:
        connection.send_error(
            msg["id"],
            "replay_integrity",
            "Replay protection could not be verified; camera changes are blocked",
        )
        return
    except StorageWriteError:
        connection.send_error(
            msg["id"],
            "storage_failed",
            "The privacy intent was not durably saved",
        )
        return
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("pause_camera failed (%s)", type(err).__name__)
        connection.send_error(
            msg["id"], "pause_failed", "Could not complete the privacy pause"
        )
        return
    _kick_scheduler_watch(hass)
    result["state"] = await _storage(hass).async_get_state()
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/resume_camera",
        vol.Optional("camera"): _CAMERA_FIELD,
        vol.Optional("camera_entity_id"): _CAMERA_FIELD,
        vol.Optional("cameras"): _CAMERA_REFS,
        vol.Optional("operation_id"): _OPERATION_ID,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_resume_camera(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Resume one or more paused cameras."""
    if _send_recovery_pending(hass, connection, msg):
        return
    try:
        result = await async_resume_cameras(
            hass,
            _storage(hass),
            _camera_refs(msg),
            context=connection.context(msg),
            operation_id=msg.get("operation_id"),
        )
    except ReplayFilterSaturatedError:
        connection.send_error(
            msg["id"],
            "replay_saturated",
            "Replay protection is full; no camera change was applied",
        )
        return
    except ReplayIntegrityError:
        connection.send_error(
            msg["id"],
            "replay_integrity",
            "Replay protection could not be verified; camera changes are blocked",
        )
        return
    except StorageWriteError:
        connection.send_error(
            msg["id"],
            "storage_failed",
            "The privacy state was not durably saved",
        )
        return
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("resume_camera failed (%s)", type(err).__name__)
        connection.send_error(
            msg["id"], "resume_failed", "Could not complete the privacy resume"
        )
        return
    _kick_scheduler_watch(hass)
    result["state"] = await _storage(hass).async_get_state()
    connection.send_result(msg["id"], result)


def _kick_scheduler_watch(hass: HomeAssistant) -> None:
    """Reconcile scheduler watches/deadlines after pause or resume.

    Keeps manual-override detection armed from the moment a pause starts
    instead of waiting for the next minute tick.
    """
    scheduler = hass.data.get(DOMAIN, {}).get(DATA_SCHEDULER)
    if scheduler is not None:
        scheduler.async_request_tick()


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_state"})
@websocket_api.require_admin
@websocket_api.async_response
async def _ws_get_state(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return persisted state plus current Frigate camera discovery."""
    state = await _storage(hass).async_get_state()
    state["recovery_ready"] = hass.data.get(DOMAIN, {}).get(
        DATA_RECOVERY_READY, False
    )
    state["cameras"] = discover_frigate_cameras(hass)
    connection.send_result(msg["id"], state)


def async_register_commands(hass: HomeAssistant) -> None:
    """Register all websocket commands."""
    for handler in (
        _ws_list_cameras,
        _ws_get_schedules,
        _ws_set_schedule,
        _ws_pause_camera,
        _ws_resume_camera,
        _ws_get_state,
    ):
        websocket_api.async_register_command(hass, handler)


def _camera_refs(msg: dict[str, Any]) -> list[str] | None:
    refs: list[str] = []
    for key in ("cameras", "camera", "camera_entity_id"):
        value = msg.get(key)
        if isinstance(value, list):
            refs.extend(str(item) for item in value if item)
        elif value:
            refs.append(str(value))
    return refs or None
