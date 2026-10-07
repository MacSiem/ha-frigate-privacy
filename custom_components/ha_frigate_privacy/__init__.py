"""Frigate Privacy integration entry points."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, Unauthorized

from .const import (
    DATA_FRONTEND_REGISTERED,
    DATA_PANEL_REGISTERED,
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
from .frontend import (
    async_register_card, async_register_panel, async_register_static,
    async_unregister_card, async_unregister_panel,
)
from .scheduler import FrigatePrivacyScheduler
from .storage import FrigatePrivacyStorage
from .websocket_api import async_register_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]

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
    bucket["config_entry"] = entry
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

    if not bucket.get(DATA_FRONTEND_REGISTERED):
        await async_register_static(hass)
        await async_register_card(hass)
        bucket[DATA_FRONTEND_REGISTERED] = True
    if not bucket.get(DATA_PANEL_REGISTERED):
        bucket[DATA_PANEL_REGISTERED] = await async_register_panel(hass)
    _async_register_services(hass)

    scheduler.async_start()

    from .notifications import FrigatePrivacyNotifications
    notifier = FrigatePrivacyNotifications(hass, entry, storage)
    bucket["notifications"] = notifier
    notifier.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.debug("Frigate Privacy set up (entry_id=%s)", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    bucket = hass.data.get(DOMAIN, {})
    if notifier := bucket.pop("notifications", None):
        await notifier.async_stop()
    bucket.pop("config_entry", None)
    if scheduler := bucket.pop(DATA_SCHEDULER, None):
        await scheduler.async_stop()
    bucket.pop(DATA_STORAGE, None)
    if bucket.pop(DATA_PANEL_REGISTERED, False):
        async_unregister_panel(hass)
    if bucket.pop(DATA_FRONTEND_REGISTERED, False):
        await async_unregister_card(hass)
    if bucket.pop(DATA_SERVICES_REGISTERED, None):
        hass.services.async_remove(DOMAIN, SERVICE_PAUSE_CAMERA)
        hass.services.async_remove(DOMAIN, SERVICE_RESUME_CAMERA)
    _LOGGER.debug("Frigate Privacy unloaded (entry_id=%s)", entry.entry_id)
    return unload_ok


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
    if user is not None and user.is_admin:
        return
    # System-triggered HA actions have no user. Only an explicitly selected,
    # currently running registered automation/script may use this authority.
    # State-only entities, parent contexts and client-supplied names cannot.
    if user_id is None:
        entry = hass.data.get(DOMAIN, {}).get("config_entry")
        context_id = getattr(call.context, "id", None)
        for entity_id in (entry.options.get("trusted_actions", []) if entry else []):
            domain = entity_id.split(".", 1)[0]
            if domain not in {"automation", "script"}:
                continue
            component = hass.data.get(domain)
            entity = component.get_entity(entity_id) if component and hasattr(component, "get_entity") else None
            script = getattr(entity, "action_script" if domain == "automation" else "script", None)
            running = bool(getattr(entity, "is_on", False)) and bool(getattr(script, "is_running", False))
            # The entity context is only its latest trigger. Running single,
            # queued and parallel executions retain their own HA context.
            if running and context_id and any(
                getattr(getattr(run, "_context", None), "id", None) == context_id
                for run in getattr(script, "_runs", ())
            ):
                return
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
