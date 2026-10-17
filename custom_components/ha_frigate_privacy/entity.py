"""Shared discovery and state subscription for Frigate privacy entities."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.const import EVENT_STATE_CHANGED as HA_EVENT_STATE_CHANGED
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .const import DATA_RECOVERY_READY, DATA_STORAGE, DOMAIN, EVENT_STATE_CHANGED
from .control import discover_frigate_cameras


async def async_setup_camera_entities(hass, entry, async_add_entities, factory):
    """Add persisted/discovered cameras once, and subscribe until entry unload."""
    storage = hass.data[DOMAIN][DATA_STORAGE]
    records = await storage.async_get_paused(None) or {}
    cameras = {item['camera_id']: item for item in discover_frigate_cameras(hass)}
    known = set(records) | set(cameras)
    async_add_entities([entity for cid in sorted(known)
                        for entity in factory(storage, cid, cameras.get(cid, {}).get('name'))], True)

    @callback
    def discover(event):
        entity_id = event.data.get('entity_id', '')
        if not entity_id.startswith(('switch.', 'camera.')) or event.data.get('new_state') is None:
            return
        for camera in discover_frigate_cameras(hass):
            cid = camera['camera_id']
            if cid not in known:
                known.add(cid)
                async_add_entities(factory(storage, cid, camera.get('name')), True)

    entry.async_on_unload(hass.bus.async_listen(HA_EVENT_STATE_CHANGED, discover))


class FrigatePrivacyEntity(Entity):
    """Read durable records and propagate caller context through guarded services."""

    _attr_has_entity_name = True

    def __init__(self, storage, camera_id, name, key):
        self._storage = storage
        self._camera_id = camera_id
        self._record: dict[str, Any] | None = None
        self._attr_translation_key = key
        self._attr_unique_id = f'{DOMAIN}_{camera_id}_{key}'
        self._attr_suggested_object_id = f'{camera_id}_{key}'
        self._attr_device_info = {
            'identifiers': {(DOMAIN, camera_id)},
            'name': name or camera_id,
            'manufacturer': 'Frigate Privacy',
        }

    @property
    def available(self):
        if not self.hass.data.get(DOMAIN, {}).get(DATA_RECOVERY_READY, False):
            return False
        for camera in discover_frigate_cameras(self.hass):
            if camera['camera_id'] == self._camera_id:
                return any(item.get('state') not in {None, 'unknown', 'unavailable'}
                           for item in camera['switches'])
        return False

    @property
    def extra_state_attributes(self):
        return {'phase': (self._record or {}).get('phase', 'active')}

    async def async_update(self):
        self._record = await self._storage.async_get_paused(self._camera_id, include_inactive=True)

    async def async_added_to_hass(self):
        self.async_on_remove(self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._changed))
        self.async_on_remove(self.hass.bus.async_listen(HA_EVENT_STATE_CHANGED, self._targets_changed))
        await self.async_update()

    @callback
    def _changed(self, event):
        if event.data.get('camera_id') in {None, self._camera_id}:
            self.async_schedule_update_ha_state(True)

    @callback
    def _targets_changed(self, event):
        # Discovery and availability can change without an integration mutation.
        if event.data.get('entity_id', '').startswith(('switch.', 'camera.')):
            self.async_schedule_update_ha_state(True)

    async def _call(self, service, **data):
        await self.hass.services.async_call(
            DOMAIN, service, {'camera': self._camera_id, **data},
            blocking=True, context=self._context,
        )


def finite_deadline(record):
    """Return an aware timestamp only for a live finite privacy record."""
    if not record or not record.get('active', True):
        return None
    try:
        value = datetime.fromisoformat(record.get('ends_at') or '')
        return value if value.tzinfo is not None else None
    except (ValueError, TypeError):
        return None
