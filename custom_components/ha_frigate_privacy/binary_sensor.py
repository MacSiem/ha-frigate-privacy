"""Binary sensors for Frigate Privacy paused state."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_STORAGE, DOMAIN, EVENT_STATE_CHANGED
from .control import discover_frigate_cameras
from .storage import FrigatePrivacyStorage


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary_sensor.<cam>_privacy_active entities."""
    storage: FrigatePrivacyStorage = hass.data[DOMAIN][DATA_STORAGE]
    paused = await storage.async_get_paused(None) or {}
    discovered = discover_frigate_cameras(hass)
    names = {item["camera_id"]: item["name"] for item in discovered}
    camera_ids = sorted(set(names) | set(paused))
    async_add_entities(
        [
            FrigatePrivacyActiveSensor(storage, camera_id, names.get(camera_id))
            for camera_id in camera_ids
        ],
        True,
    )


class FrigatePrivacyActiveSensor(BinarySensorEntity):
    """Binary sensor indicating whether one camera is privacy-paused."""

    _attr_translation_key = "privacy_active"

    def __init__(
        self,
        storage: FrigatePrivacyStorage,
        camera_id: str,
        name: str | None,
    ) -> None:
        """Initialize sensor."""
        self._storage = storage
        self._camera_id = camera_id
        self._paused: dict[str, Any] | None = None
        self._attr_unique_id = f"ha_frigate_privacy_{camera_id}_privacy_active"
        self._attr_suggested_object_id = f"{camera_id}_privacy_active"
        self._attr_name = f"{name or camera_id} Privacy Active"

    @property
    def is_on(self) -> bool:
        """Return true when the camera remains privacy-paused."""
        return bool(self._paused and self._paused.get("active"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return paused state metadata."""
        if not self._paused:
            return {"camera_id": self._camera_id}
        return {
            "camera_id": self._camera_id,
            "stream_type": self._paused.get("stream_type"),
            "source": self._paused.get("source"),
            "schedule_id": self._paused.get("schedule_id"),
            "ends_at": self._paused.get("ends_at"),
            "resume_blocked": self._paused.get("resume_blocked", False),
            "resume_blocked_reason": self._paused.get("resume_blocked_reason"),
            "switches": self._paused.get("switches", []),
            "skipped": self._paused.get("skipped", []),
        }

    async def async_added_to_hass(self) -> None:
        """Update when integration state changes."""
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_event)
        )

    async def async_update(self) -> None:
        """Refresh paused state from storage."""
        self._paused = await self._storage.async_get_paused(self._camera_id)

    @callback
    def _handle_event(self, event: Event) -> None:
        camera_id = event.data.get("camera_id")
        if camera_id is None or camera_id == self._camera_id:
            self.async_schedule_update_ha_state(True)
