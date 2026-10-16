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
            if not camera_id:
                return
            record = await self.storage.async_get_record(camera_id)
            # Storage can wait. Apply the user's latest recipient/event choices
            # after that wait, immediately before reserving and sending.
            options = self.entry.options
            destination = options.get('notify_destination', '')
            if not record or not destination or destination not in notification_destinations(self.hass):
                return
            phase = record.get('phase')
            scheduled = record.get('source') == 'schedule'
            if phase in {'partial', 'error'} and options.get('notify_errors', True):
                message = 'Privacy is not fully confirmed. An administrator should review the target evidence in Frigate Privacy.'
            elif phase == 'paused' and options.get('notify_scheduled' if scheduled else 'notify_paused', False):
                message = ('Scheduled privacy scope is paused.' if scheduled else 'The selected privacy scope is paused.') + ' Check video status for cameras without supported stop actions.'
            elif phase == 'active' and options.get('notify_scheduled' if scheduled else 'notify_resumed', False) and record.get('reason') != 'manual_override':
                message = ('The scheduled privacy window ended' if scheduled else 'The privacy window ended') + ' and the saved targets were restored after verification.'
            else:
                return
            signature = (destination, phase, record.get('generation'), record.get('operation_id'), record.get('resume_operation_id'))
            if self._last.get(camera_id) == signature:
                return
            # Reserve before delivery: repeated state events must not flood a phone.
            self._last[camera_id] = signature
            notification_id = 'ha_frigate_privacy_optional_' + hashlib.sha256(camera_id.encode()).hexdigest()[:16]
            await self._async_deliver(destination, message, notification_id)

    def snapshot(self):
        """Read saved preferences only; never imply confirmed delivery."""
        options = self.entry.options
        destination = options.get('notify_destination', '')
        destinations = notification_destinations(self.hass)
        return {
            'destination': destination,
            'label': destinations.get(destination, destination),
            'available': self._destination_available(destination, destinations),
            'events': {name: bool(options.get('notify_' + name, name == 'errors'))
                       for name in ('errors', 'paused', 'resumed', 'scheduled')},
        }

    def _destination_available(self, destination, destinations):
        if not destination or destination not in destinations:
            return False
        if destination.startswith('entity:'):
            return self.hass.services.has_service('notify', 'send_message')
        domain, service = destination.split('.', 1)
        return self.hass.services.has_service(domain, service)

    async def async_test(self):
        """Explicit generic test of the latest saved channel; no state or dedup writes."""
        destination = self.entry.options.get('notify_destination', '')
        if not self._destination_available(destination, notification_destinations(self.hass)):
            return {'status': 'no_channel'}
        status = await self._async_deliver(
            destination, 'Frigate Privacy — test', 'ha_frigate_privacy_notification_test'
        )
        return {'status': status}

    async def _async_deliver(self, destination, message, notification_id):
        data = {'title': 'Frigate Privacy', 'message': message}
        if destination == 'persistent_notification.create':
            data['notification_id'] = notification_id
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
            return 'error'
        return 'ha_accepted'

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
