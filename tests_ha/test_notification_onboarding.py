"""Saved destinations and explicit tests in the actual HA runtime."""
import asyncio
from copy import deepcopy
from unittest.mock import patch
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.ha_frigate_privacy.const import DOMAIN, EVENT_STATE_CHANGED
from tests_ha.test_frontend import _setup


@pytest.mark.parametrize('destination,domain,service,entity', [
    ('persistent_notification.create', 'persistent_notification', 'create', None),
    ('notify.qa_phone', 'notify', 'qa_phone', None),
    ('entity:notify.qa_phone', 'notify', 'send_message', 'notify.qa_phone'),
])
async def test_explicit_test_is_generic_and_has_no_privacy_or_preference_writes(hass, destination, domain, service, entity):
    entry = await _setup(hass)
    calls = []
    async def delivered(call): calls.append(dict(call.data))
    hass.services.async_register(domain, service, delivered)
    if entity: hass.states.async_set(entity, 'unknown', {'friendly_name': 'QA destination'})
    options = {'notify_destination': destination, 'notify_errors': False, 'notify_paused': False,
               'notify_resumed': False, 'notify_scheduled': False, 'trusted_actions': []}
    hass.config_entries.async_update_entry(entry, options=options)
    notifier = hass.data[DOMAIN]['notifications']
    storage = hass.data[DOMAIN]['storage']
    state = deepcopy(await storage.async_get_state())
    last = deepcopy(notifier._last)
    # Observe the real event bus: HA uses slots and instance methods are read-only.
    events = []
    remove_listener = hass.bus.async_listen(EVENT_STATE_CHANGED, lambda event: events.append(event))
    # Test requires no record read/save and emits no synthetic camera event.
    with patch.object(storage, 'async_get_record', side_effect=AssertionError('test read camera record')), \
         patch.object(storage._store, 'async_save', side_effect=AssertionError('test saved storage')), \
         patch.object(hass.config_entries, 'async_update_entry', side_effect=AssertionError('test wrote preferences')):
        assert await notifier.async_test() == {'status': 'ha_accepted'}
        await hass.async_block_till_done()
        assert events == []
    remove_listener()
    assert len(calls) == 1 and calls[0]['message'] == 'Frigate Privacy — test'
    assert calls[0]['title'] == 'Frigate Privacy'
    if entity: assert calls[0]['entity_id'] == entity
    if domain == 'persistent_notification':
        assert calls[0]['notification_id'] == 'ha_frigate_privacy_notification_test'
        assert not calls[0]['notification_id'].startswith('ha_frigate_privacy_optional_')
    assert dict(entry.options) == options
    assert await storage.async_get_state() == state and notifier._last == last
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize('destination', ['', 'notify.missing', 'entity:notify.unavailable', 'notify.reload', 'notify.send_message', 'shell_command.execute', 'persistent_notification.create'])
async def test_no_saved_available_destination_never_calls_a_service(hass, destination):
    entry = await _setup(hass)
    hass.states.async_set('notify.unavailable', 'unavailable')
    hass.services.async_remove('persistent_notification', 'create')
    hass.config_entries.async_update_entry(entry, options={'notify_destination': destination})
    notifier = hass.data[DOMAIN]['notifications']
    with patch.object(type(hass.services), 'async_call', side_effect=AssertionError('no channel must not call HA')):
        assert await notifier.async_test() == {'status': 'no_channel'}
    assert notifier.snapshot()['available'] is False
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_explicit_test_uses_latest_preferences_and_safe_failure_without_retry(hass):
    entry = await _setup(hass)
    notifier = hass.data[DOMAIN]['notifications']
    calls = []
    async def failure(call):
        calls.append(call.service)
        raise RuntimeError('private-token-and-address')
    hass.services.async_register('notify', 'qa_new', failure)
    hass.config_entries.async_update_entry(entry, options={'notify_destination': 'notify.qa_old'})
    hass.config_entries.async_update_entry(entry, options={'notify_destination': 'notify.qa_new'})
    assert await notifier.async_test() == {'status': 'error'}
    await hass.async_block_till_done()
    assert calls == ['qa_new']
    hass.config_entries.async_update_entry(entry, options={'notify_destination': ''})
    assert await notifier.async_test() == {'status': 'no_channel'}
    assert calls == ['qa_new'] and notifier._last == {}
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_cancelled_test_never_reports_success_or_retries(hass):
    entry = await _setup(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def waiting(call):
        calls.append(call.service)
        entered.set()
        await release.wait()
    hass.services.async_register('notify', 'qa_wait', waiting)
    hass.config_entries.async_update_entry(entry, options={'notify_destination': 'notify.qa_wait'})
    notifier = hass.data[DOMAIN]['notifications']
    task = asyncio.create_task(notifier.async_test())
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    release.set()
    assert calls == ['qa_wait'] and notifier._last == {}
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_snapshot_defaults_latest_flags_and_saved_unavailable_destination(hass):
    entry = await _setup(hass)
    notifier = hass.data[DOMAIN]['notifications']
    assert notifier.snapshot() == {'destination': '', 'label': 'Off', 'available': False,
                                  'events': {'errors': True, 'paused': False, 'resumed': False, 'scheduled': False}}
    hass.config_entries.async_update_entry(entry, options={'notify_destination': 'entity:notify.saved',
        'notify_errors': False, 'notify_paused': True, 'notify_resumed': True, 'notify_scheduled': True,
        'trusted_actions': ['script.private']})
    snapshot = notifier.snapshot()
    assert snapshot['destination'] == 'entity:notify.saved' and snapshot['available'] is False
    assert snapshot['events'] == {'errors': False, 'paused': True, 'resumed': True, 'scheduled': True}
    assert 'trusted_actions' not in snapshot and 'script.private' not in str(snapshot)
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize('field', ['destination', 'message', 'camera'])
async def test_websocket_rejects_client_notification_payload(hass, hass_ws_client, field):
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    notifier = hass.data[DOMAIN]['notifications']
    with patch.object(notifier, 'async_test', side_effect=AssertionError('invalid schema reached delivery')):
        await client.send_json({'id': 1, 'type': DOMAIN + '/test_notification', field: 'private'})
        response = await client.receive_json()
    assert not response['success'] and response['error']['code'] == 'invalid_format'
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_native_options_keeps_missing_saved_destination_and_localization_keys(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN,
        options={'notify_destination': 'notify.gone', 'trusted_actions': []})
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    schema = flow['data_schema'].schema
    key = next(key for key in schema if key.schema == 'notify_destination')
    config = schema[key].config
    assert key.default() == 'notify.gone'
    assert config['translation_key'] == 'notification_destination'
    selected = next(item for item in config['options'] if item['value'] == 'notify.gone')
    assert 'unavailable' in selected['label']
    result = await hass.config_entries.options.async_configure(flow['flow_id'], {
        'notify_destination': 'notify.gone', 'notify_errors': False, 'notify_paused': True,
        'notify_resumed': False, 'notify_scheduled': True, 'trusted_actions': [],
    })
    assert result['type'] == 'create_entry' and entry.options['notify_destination'] == 'notify.gone'


async def test_test_does_not_consume_normal_dedup_and_failed_event_reservation_survives(hass):
    entry = await _setup(hass)
    notifier = hass.data[DOMAIN]['notifications']
    storage = hass.data[DOMAIN]['storage']
    calls = []
    async def failure(call):
        calls.append(dict(call.data))
        raise RuntimeError('transport failed')
    hass.services.async_register('notify', 'qa_phone', failure)
    hass.config_entries.async_update_entry(entry, options={'notify_destination': 'notify.qa_phone', 'notify_errors': True})
    await storage.async_set_paused('private_camera', {'phase': 'error', 'operation_id': 'same-operation'})
    await asyncio.gather(notifier._notify('private_camera'), notifier._notify('private_camera'))
    assert len(calls) == 1
    reservation = deepcopy(notifier._last)
    assert await notifier.async_test() == {'status': 'error'}
    assert notifier._last == reservation
    await notifier._notify('private_camera')
    assert len(calls) == 2, 'failed event remains reserved; explicit test is independent'
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize('saved,ui_value', [('', 'off'), ('persistent_notification.create', 'home_assistant')])
async def test_localized_destination_values_preserve_the_saved_channel(hass, saved, ui_value):
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN, options={'notify_destination': saved})
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    schema = flow['data_schema'].schema
    key = next(key for key in schema if key.schema == 'notify_destination')
    assert key.default() == ui_value
    assert any(option['value'] == ui_value for option in schema[key].config['options'])
    result = await hass.config_entries.options.async_configure(flow['flow_id'], {
        'notify_destination': ui_value, 'notify_errors': True, 'notify_paused': False,
        'notify_resumed': False, 'notify_scheduled': False, 'trusted_actions': []})
    assert result['type'] == 'create_entry'
    assert entry.options['notify_destination'] == saved
    assert entry.options['trusted_actions'] == []
