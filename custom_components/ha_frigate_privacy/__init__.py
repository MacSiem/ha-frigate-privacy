"""Frigate Privacy integration entry points."""

from __future__ import annotations

import logging
import os

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, Unauthorized

from .const import (
    DATA_FRONTEND_REGISTERED,
    DATA_RECOVERY_READY,
    DATA_SCHEDULER,
    DATA_SERVICES_REGISTERED,
    DATA_STORAGE,
    DATA_WS_REGISTERED,
    DOMAIN,
    SERVICE_PAUSE_CAMERA,
    SERVICE_RESUME_CAMERA,
    STREAM_TYPES,
    VERSION,
)
from .control import async_pause_cameras, async_resume_cameras
from .scheduler import FrigatePrivacyScheduler
from .storage import FrigatePrivacyStorage
from .websocket_api import async_register_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]

_CARD_FILENAME = "ha-frigate-privacy-card.js"
_CARD_URL_PATH = f"/{DOMAIN}/{_CARD_FILENAME}"
_CARD_PACKAGE_DIR = "www"

_CAMERA_REF = vol.All(str, vol.Length(min=1, max=255))
_CAMERA_FIELD = vol.Any(
    _CAMERA_REF,
    vol.All([_CAMERA_REF], vol.Length(min=1, max=64)),
)
_SERVICE_PAUSE_SCHEMA = vol.Schema(
    {
        vol.Optional("camera"): _CAMERA_FIELD,
        vol.Optional("camera_entity_id"): _CAMERA_FIELD,
        vol.Optional("duration_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
        vol.Optional("stream_type", default="all"): vol.In(STREAM_TYPES),
        vol.Optional("operation_id"): vol.All(
            str, vol.Length(min=1, max=128)
        ),
    }
)
_SERVICE_RESUME_SCHEMA = vol.Schema(
    {
        vol.Optional("camera"): _CAMERA_FIELD,
        vol.Optional("camera_entity_id"): _CAMERA_FIELD,
        vol.Optional("operation_id"): vol.All(
            str, vol.Length(min=1, max=128)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Frigate Privacy from a config entry."""
    bucket = hass.data.setdefault(DOMAIN, {})
    storage = FrigatePrivacyStorage(hass)
    await storage.async_load()
    bucket[DATA_STORAGE] = storage
    bucket[DATA_RECOVERY_READY] = False

    scheduler = FrigatePrivacyScheduler(hass, storage)
    bucket[DATA_SCHEDULER] = scheduler

    # Frigate entities can appear after config entries are loaded. Never run
    # authoritative recovery before HA has started, because treating a load-
    # order absence as target removal would destroy exact-target evidence.
    # When HA is already running, finish a full schedule/deadline reconcile
    # before exposing mutation endpoints.
    if hass.is_running:
        await scheduler.async_tick()

    if not bucket.get(DATA_WS_REGISTERED):
        async_register_commands(hass)
        bucket[DATA_WS_REGISTERED] = True

    await _async_register_frontend(hass)
    _async_register_services(hass)

    scheduler.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("Frigate Privacy set up (entry_id=%s)", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    bucket = hass.data.get(DOMAIN, {})
    if scheduler := bucket.pop(DATA_SCHEDULER, None):
        await scheduler.async_stop()
    bucket.pop(DATA_STORAGE, None)
    if bucket.pop(DATA_SERVICES_REGISTERED, None):
        hass.services.async_remove(DOMAIN, SERVICE_PAUSE_CAMERA)
        hass.services.async_remove(DOMAIN, SERVICE_RESUME_CAMERA)
    _LOGGER.debug("Frigate Privacy unloaded (entry_id=%s)", entry.entry_id)
    return unload_ok


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register the bundled Lovelace card under /ha_frigate_privacy/."""
    bucket = hass.data.setdefault(DOMAIN, {})
    if bucket.get(DATA_FRONTEND_REGISTERED):
        return

    card_path = os.path.join(
        os.path.dirname(__file__), _CARD_PACKAGE_DIR, _CARD_FILENAME
    )
    if not await hass.async_add_executor_job(os.path.isfile, card_path):
        _LOGGER.error("Bundled Frigate Privacy card missing at %s", card_path)
        return

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                f"/{DOMAIN}", os.path.dirname(card_path), cache_headers=False
            )
        ]
    )
    add_extra_js_url(hass, f"{_CARD_URL_PATH}?v={VERSION}")
    bucket[DATA_FRONTEND_REGISTERED] = True
    _LOGGER.debug("Registered Frigate Privacy Lovelace card at %s", _CARD_URL_PATH)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once per HA process."""
    bucket = hass.data.setdefault(DOMAIN, {})
    if bucket.get(DATA_SERVICES_REGISTERED):
        return

    async def _handle_pause(call: ServiceCall) -> None:
        await _async_require_admin(hass, call)
        _require_recovery_ready(hass)
        await async_pause_cameras(
            hass,
            hass.data[DOMAIN][DATA_STORAGE],
            _service_camera_refs(call),
            duration_minutes=call.data.get("duration_minutes"),
            stream_type=call.data.get("stream_type", "all"),
            source="manual",
            context=call.context,
            operation_id=call.data.get("operation_id"),
        )

    async def _handle_resume(call: ServiceCall) -> None:
        await _async_require_admin(hass, call)
        _require_recovery_ready(hass)
        await async_resume_cameras(
            hass,
            hass.data[DOMAIN][DATA_STORAGE],
            _service_camera_refs(call),
            context=call.context,
            operation_id=call.data.get("operation_id"),
        )

    hass.services.async_register(
        DOMAIN, SERVICE_PAUSE_CAMERA, _handle_pause, schema=_SERVICE_PAUSE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME_CAMERA, _handle_resume, schema=_SERVICE_RESUME_SCHEMA
    )
    bucket[DATA_SERVICES_REGISTERED] = True


async def _async_require_admin(
    hass: HomeAssistant, call: ServiceCall
) -> None:
    """Reject service calls that cannot be attributed to an administrator."""
    user_id = call.context.user_id
    user = await hass.auth.async_get_user(user_id) if user_id else None
    if user is None or not user.is_admin:
        raise Unauthorized()


def _require_recovery_ready(hass: HomeAssistant) -> None:
    """Reject mutations until startup recovery has reliable Frigate inputs."""
    if not hass.data.get(DOMAIN, {}).get(DATA_RECOVERY_READY, False):
        raise HomeAssistantError(
            "Frigate Privacy is still reconciling persisted privacy state"
        )


def _service_camera_refs(call: ServiceCall) -> list[str] | None:
    refs: list[str] = []
    for key in ("camera", "camera_entity_id"):
        value = call.data.get(key)
        if isinstance(value, list):
            refs.extend(str(item) for item in value if item)
        elif value:
            refs.append(str(value))
    return refs or None
