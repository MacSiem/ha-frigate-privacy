"""Single-camera privacy timer buttons using guarded integration services."""
from homeassistant.components.button import ButtonEntity
from .const import SERVICE_PAUSE_CAMERA
from .entity import FrigatePrivacyEntity, async_setup_camera_entities


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_camera_entities(hass, entry, async_add_entities,
        lambda storage, cid, name: [FrigatePrivacyTimerButton(storage, cid, name, minutes)
                                    for minutes in (15, 30, 60)])


class FrigatePrivacyTimerButton(FrigatePrivacyEntity, ButtonEntity):
    _attr_icon = 'mdi:timer-lock-outline'

    def __init__(self, storage, camera_id, name, minutes):
        super().__init__(storage, camera_id, name, f'privacy_{minutes}_minutes')
        self._minutes = minutes

    async def async_press(self):
        await self._call(SERVICE_PAUSE_CAMERA, duration_minutes=self._minutes)
