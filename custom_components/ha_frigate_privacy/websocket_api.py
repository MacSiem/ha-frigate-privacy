"""WebSocket API for Frigate Privacy."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import (
    DATA_SCHEDULER,
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
from .storage import FrigatePrivacyStorage

_LOGGER = logging.getLogger(__name__)


def _storage(hass: HomeAssistant) -> FrigatePrivacyStorage:
    return hass.data[DOMAIN][DATA_STORAGE]


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
        vol.Optional("schedule_id"): str,
        vol.Optional("schedules"): [dict],
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
    storage = _storage(hass)
    action = msg["action"]
    try:
        if action == "upsert":
            if "schedule" not in msg:
                raise ValueError("schedule is required")
            schedule = await storage.async_upsert_schedule(msg["schedule"])
            result = {"schedule": schedule}
        elif action == "delete":
            schedule_id = msg.get("schedule_id")
            if not schedule_id:
                raise ValueError("schedule_id is required")
            result = {"deleted": await storage.async_delete_schedule(schedule_id)}
        elif action == "replace_all":
            result = {
                "schedules": await storage.async_replace_schedules(
                    msg.get("schedules") or []
                )
            }
        else:
            result = {"schedules": await storage.async_replace_schedules([])}
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_payload", str(err))
        return
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("set_schedule failed: %s", err)
        connection.send_error(msg["id"], "set_schedule_failed", str(err))
        return

    hass.bus.async_fire(EVENT_STATE_CHANGED, {"schedules": True})
    if scheduler := hass.data[DOMAIN].get(DATA_SCHEDULER):
        hass.async_create_task(scheduler.async_tick())
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/pause_camera",
        vol.Optional("camera"): vol.Any(str, [str]),
        vol.Optional("camera_entity_id"): vol.Any(str, [str]),
        vol.Optional("cameras"): [str],
        vol.Optional("duration_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
        vol.Optional("stream_type", default="all"): vol.In(STREAM_TYPES),
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
    result = await async_pause_cameras(
        hass,
        _storage(hass),
        _camera_refs(msg),
        duration_minutes=msg.get("duration_minutes"),
        stream_type=msg["stream_type"],
        source="manual",
    )
    result["state"] = await _storage(hass).async_get_state()
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/resume_camera",
        vol.Optional("camera"): vol.Any(str, [str]),
        vol.Optional("camera_entity_id"): vol.Any(str, [str]),
        vol.Optional("cameras"): [str],
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
    result = await async_resume_cameras(hass, _storage(hass), _camera_refs(msg))
    result["state"] = await _storage(hass).async_get_state()
    connection.send_result(msg["id"], result)


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
