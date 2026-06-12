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

from .const import (
    DATA_FRONTEND_REGISTERED,
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
from .scheduler import async_start_scheduler
from .storage import FrigatePrivacyStorage
from .websocket_api import async_register_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]

_CARD_FILENAME = "ha-frigate-privacy-card.js"
_CARD_URL_PATH = f"/{DOMAIN}/{_CARD_FILENAME}"
_CARD_PACKAGE_DIR = "www"

_CAMERA_FIELD = vol.Any(str, [str])
_SERVICE_PAUSE_SCHEMA = vol.Schema(
    {
        vol.Optional("camera"): _CAMERA_FIELD,
        vol.Optional("camera_entity_id"): _CAMERA_FIELD,
        vol.Optional("duration_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
        vol.Optional("stream_type", default="all"): vol.In(STREAM_TYPES),
    }
)
_SERVICE_RESUME_SCHEMA = vol.Schema(
    {
        vol.Optional("camera"): _CAMERA_FIELD,
        vol.Optional("camera_entity_id"): _CAMERA_FIELD,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Frigate Privacy from a config entry."""
    bucket = hass.data.setdefault(DOMAIN, {})
    storage = FrigatePrivacyStorage(hass)
    await storage.async_load()
    bucket[DATA_STORAGE] = storage

    if not bucket.get(DATA_WS_REGISTERED):
        async_register_commands(hass)
        bucket[DATA_WS_REGISTERED] = True

    await _async_register_frontend(hass)
    _async_register_services(hass)

    if DATA_SCHEDULER not in bucket:
        bucket[DATA_SCHEDULER] = async_start_scheduler(hass, storage)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("Frigate Privacy set up (entry_id=%s)", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    bucket = hass.data.get(DOMAIN, {})
    if scheduler := bucket.pop(DATA_SCHEDULER, None):
        scheduler.async_stop()
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
    if not os.path.isfile(card_path):
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
        await async_pause_cameras(
            hass,
            hass.data[DOMAIN][DATA_STORAGE],
            _service_camera_refs(call),
            duration_minutes=call.data.get("duration_minutes"),
            stream_type=call.data.get("stream_type", "all"),
            source="service",
        )

    async def _handle_resume(call: ServiceCall) -> None:
        await async_resume_cameras(
            hass,
            hass.data[DOMAIN][DATA_STORAGE],
            _service_camera_refs(call),
        )

    hass.services.async_register(
        DOMAIN, SERVICE_PAUSE_CAMERA, _handle_pause, schema=_SERVICE_PAUSE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME_CAMERA, _handle_resume, schema=_SERVICE_RESUME_SCHEMA
    )
    bucket[DATA_SERVICES_REGISTERED] = True


def _service_camera_refs(call: ServiceCall) -> list[str] | None:
    refs: list[str] = []
    for key in ("camera", "camera_entity_id"):
        value = call.data.get(key)
        if isinstance(value, list):
            refs.extend(str(item) for item in value if item)
        elif value:
            refs.append(str(value))
    return refs or None
