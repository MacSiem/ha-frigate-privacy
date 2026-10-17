"""Durable deadline and last control outcome sensors."""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from .const import DATA_RECOVERY_READY, DATA_STORAGE, DOMAIN, EVENT_STATE_CHANGED
from .entity import FrigatePrivacyEntity, async_setup_camera_entities, finite_deadline


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_camera_entities(hass, entry, async_add_entities,
        lambda storage, cid, name: [FrigatePrivacyDeadline(storage, cid, name, 'privacy_until')])
    async_add_entities([FrigatePrivacyOutcome(hass.data[DOMAIN][DATA_STORAGE])], True)


class FrigatePrivacyDeadline(FrigatePrivacyEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        return finite_deadline(self._record)


class FrigatePrivacyOutcome(SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = 'last_outcome'
    _attr_unique_id = f'{DOMAIN}_last_outcome'
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ['confirmed', 'partial', 'error']
    _attr_device_info = {'identifiers': {(DOMAIN, DOMAIN)}, 'name': 'Frigate Privacy'}
    _attr_native_value = None

    def __init__(self, storage):
        self._storage = storage

    @property
    def available(self):
        return bool(self.hass.data.get(DOMAIN, {}).get(DATA_RECOVERY_READY, False))

    async def async_update(self):
        outcome = (await self._storage.async_get_state()).get('last_outcome')
        self._attr_native_value = outcome if outcome in self._attr_options else None

    async def async_added_to_hass(self):
        self.async_on_remove(self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._changed))
        await self.async_update()

    @callback
    def _changed(self, event):
        self.async_schedule_update_ha_state(True)
