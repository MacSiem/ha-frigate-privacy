"""Guarded per-camera privacy switches."""
from homeassistant.components.switch import SwitchEntity
from .const import SERVICE_PAUSE_CAMERA, SERVICE_RESUME_CAMERA
from .entity import FrigatePrivacyEntity, async_setup_camera_entities


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_camera_entities(hass, entry, async_add_entities,
        lambda storage, cid, name: [FrigatePrivacySwitch(storage, cid, name, 'privacy')])


class FrigatePrivacySwitch(FrigatePrivacyEntity, SwitchEntity):
    _attr_icon = 'mdi:cctv-off'

    @property
    def is_on(self):
        if self._record and self._record.get('active', True):
            return True if self._record.get('phase') == 'paused' else None
        return False

    async def async_turn_on(self, **kwargs):
        await self._call(SERVICE_PAUSE_CAMERA)

    async def async_turn_off(self, **kwargs):
        await self._call(SERVICE_RESUME_CAMERA)
