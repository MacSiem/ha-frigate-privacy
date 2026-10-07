"""Optional privacy-safe notifications; camera control remains independent."""
from __future__ import annotations
import asyncio
import hashlib
import logging
from .const import EVENT_STATE_CHANGED
from .config_flow import notification_destinations
_LOGGER = logging.getLogger(__name__)

class FrigatePrivacyNotifications:
    def __init__(self, hass, entry, storage):
        self.hass, self.entry, self.storage = hass, entry, storage
        self._unsubscribe = None
        self._tasks = set()
        self._last = {}
        self._lock = asyncio.Lock()

    def async_start(self):
        self._unsubscribe = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._event)

    async def _event(self, event):
        if not self.entry.options.get('notify_destination'):
            return
        task = self.hass.async_create_task(self._notify(event.data.get('camera_id')))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _notify(self, camera_id):
        async with self._lock:
            options = self.entry.options
            destination = options.get('notify_destination', '')
            if not camera_id or not destination or destination not in notification_destinations(self.hass):
                return
            record = await self.storage.async_get_record(camera_id)
            if not record:
                return
            phase = record.get('phase')
            if phase in {'partial', 'error'} and options.get('notify_errors', True):
                message = 'Privacy is not fully confirmed. An administrator should review the target evidence in Frigate Privacy.'
            elif phase == 'paused' and options.get('notify_paused', False):
                message = 'The selected privacy scope is paused. Check video status for cameras without supported stop actions.'
            elif phase == 'active' and options.get('notify_resumed', False) and record.get('reason') != 'manual_override':
                message = 'The privacy window ended and the saved targets were restored after verification.'
            else:
                return
            signature = (destination, phase, record.get('generation'), record.get('operation_id'), record.get('resume_operation_id'))
            if self._last.get(camera_id) == signature:
                return
            # Reserve before delivery: repeated state events must not flood a phone.
            self._last[camera_id] = signature
            data = {'title':'Frigate Privacy', 'message':message}
            if destination == 'persistent_notification.create':
                data['notification_id'] = 'ha_frigate_privacy_optional_' + hashlib.sha256(camera_id.encode()).hexdigest()[:16]
                domain, service = 'persistent_notification', 'create'
            elif destination.startswith('entity:'):
                data['entity_id'] = destination.removeprefix('entity:')
                domain, service = 'notify', 'send_message'
            else:
                domain, service = destination.split('.', 1)
            try:
                await self.hass.services.async_call(domain, service, data, blocking=True)
            except Exception as error:
                _LOGGER.warning('Optional privacy notification failed (%s)', type(error).__name__)

    async def async_stop(self):
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._last.clear()
