"""User-selected notifications must not change privacy control or disclose topology."""
from homeassistant.core import HomeAssistant
from custom_components.ha_frigate_privacy.const import DOMAIN, EVENT_STATE_CHANGED
from tests_ha.test_frontend import _setup

async def test_optional_notifications_are_generic_and_deduplicate(hass: HomeAssistant, hass_ws_client):
    entry = await _setup(hass)
    hass.config_entries.async_update_entry(entry, options={
        'notify_destination':'persistent_notification.create', 'notify_errors':True,
        'notify_paused':False, 'notify_resumed':False,
    })
    storage = hass.data[DOMAIN]['storage']
    await storage.async_set_paused('private_camera_name', {'phase':'partial', 'operation_id':'private-operation', 'reason':'private-address'})
    client = await hass_ws_client(hass)
    async def notifications():
        await client.send_json({'id':1,'type':'persistent_notification/get'})
        response = await client.receive_json()
        assert response['success']
        return response['result']
    hass.bus.async_fire(EVENT_STATE_CHANGED, {'camera_id':'private_camera_name'})
    await hass.async_block_till_done()
    first = await notifications()
    own = [n for n in first if n['title'].startswith('Frigate Privacy')]
    assert len(own) == 1
    assert 'not fully confirmed' in own[0]['message']
    assert 'private_' not in str(own) and 'private-' not in str(own)
    hass.bus.async_fire(EVENT_STATE_CHANGED, {'camera_id':'private_camera_name'})
    await hass.async_block_till_done()
    # IDs must be unique per request on the same websocket.
    await client.send_json({'id':2,'type':'persistent_notification/get'})
    assert (await client.receive_json())['result'] == first
    assert await hass.config_entries.async_unload(entry.entry_id)

async def test_default_extra_notifications_are_off(hass: HomeAssistant, hass_ws_client):
    entry = await _setup(hass)
    await hass.data[DOMAIN]['storage'].async_set_paused('private_camera_name', {'phase':'error'})
    hass.bus.async_fire(EVENT_STATE_CHANGED, {'camera_id':'private_camera_name'})
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    await client.send_json({'id':1,'type':'persistent_notification/get'})
    assert (await client.receive_json())['result'] == []
    assert await hass.config_entries.async_unload(entry.entry_id)

async def test_notification_failure_does_not_change_privacy_and_unload_stops_delivery(hass: HomeAssistant):
    entry = await _setup(hass)
    delivered = []
    async def fail_delivery(call):
        delivered.append(call.data)
        raise RuntimeError('test transport unavailable')
    hass.services.async_register('notify', 'qa_phone', fail_delivery)
    hass.config_entries.async_update_entry(entry, options={
        'notify_destination':'notify.qa_phone', 'notify_errors':True,
    })
    storage = hass.data[DOMAIN]['storage']
    await storage.async_set_paused('qa_camera', {'phase':'error', 'operation_id':'qa-first'})
    original = await storage.async_get_record('qa_camera')
    hass.bus.async_fire(EVENT_STATE_CHANGED, {'camera_id':'qa_camera'})
    await hass.async_block_till_done()
    assert len(delivered) == 1
    assert await storage.async_get_record('qa_camera') == original
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.bus.async_fire(EVENT_STATE_CHANGED, {'camera_id':'qa_other_camera'})
    await hass.async_block_till_done()
    assert len(delivered) == 1

async def test_notify_entity_obeys_selected_events_and_live_preferences(hass: HomeAssistant):
    entry = await _setup(hass)
    delivered = []
    async def deliver(call):
        delivered.append(dict(call.data))
    hass.services.async_register('notify', 'send_message', deliver)
    hass.states.async_set('notify.qa_phone', 'unknown')
    hass.config_entries.async_update_entry(entry, options={
        'notify_destination':'entity:notify.qa_phone', 'notify_errors':False,
        'notify_paused':True, 'notify_resumed':True,
    })
    storage = hass.data[DOMAIN]['storage']
    for phase in ('error', 'paused', 'active'):
        await storage.async_set_paused('private_name', {'phase':phase, 'operation_id':'private-operation'})
        hass.bus.async_fire(EVENT_STATE_CHANGED, {'camera_id':'private_name'})
        await hass.async_block_till_done()
    assert len(delivered) == 2
    assert all(item['entity_id'] == 'notify.qa_phone' for item in delivered)
    assert 'paused' in delivered[0]['message'] and 'restored' in delivered[1]['message']
    assert 'private' not in str(delivered)
    hass.config_entries.async_update_entry(entry, options={'notify_destination':''})
    await storage.async_set_paused('private_name', {'phase':'paused', 'operation_id':'new-operation'})
    hass.bus.async_fire(EVENT_STATE_CHANGED, {'camera_id':'private_name'})
    await hass.async_block_till_done()
    assert len(delivered) == 2
    assert await hass.config_entries.async_unload(entry.entry_id)

async def test_scheduled_notifications_are_selected_independently(hass: HomeAssistant):
    entry = await _setup(hass)
    delivered = []
    async def deliver(call):
        delivered.append(dict(call.data))
    hass.services.async_register('notify', 'qa_phone', deliver)
    hass.config_entries.async_update_entry(entry, options={
        'notify_destination':'notify.qa_phone', 'notify_errors':False,
        'notify_paused':False, 'notify_resumed':False, 'notify_scheduled':True,
    })
    storage = hass.data[DOMAIN]['storage']
    for phase, source in [('paused','manual'), ('active','manual'), ('paused','schedule'), ('active','schedule')]:
        await storage.async_set_paused('qa_camera', {'phase':phase, 'source':source, 'operation_id':source})
        hass.bus.async_fire(EVENT_STATE_CHANGED, {'camera_id':'qa_camera'})
        await hass.async_block_till_done()
    assert len(delivered) == 2, 'scheduled start/end is selectable without manual on/off events'
    assert 'scheduled' in delivered[0]['message'].lower()
    assert 'restored' in delivered[1]['message'].lower()
    assert await hass.config_entries.async_unload(entry.entry_id)

async def test_changing_notification_recipient_while_storage_waits_rechecks_preferences(hass: HomeAssistant):
    import asyncio
    from unittest.mock import patch
    entry = await _setup(hass)
    delivered = []
    async def deliver(call):
        delivered.append(call.service)
    hass.services.async_register('notify','qa_old',deliver)
    hass.services.async_register('notify','qa_new',deliver)
    storage = hass.data[DOMAIN]['storage']
    notifier = hass.data[DOMAIN]['notifications']
    for replacement in ('notify.qa_new',''):
        hass.config_entries.async_update_entry(entry, options={'notify_destination':'notify.qa_old','notify_errors':True})
        entered, release = asyncio.Event(), asyncio.Event()
        async def waiting_record(camera_id):
            entered.set()
            await release.wait()
            return {'phase':'error','operation_id':replacement}
        with patch.object(storage,'async_get_record',waiting_record):
            task = hass.async_create_task(notifier._notify('qa_camera'))
            await asyncio.wait_for(entered.wait(), 2)
            hass.config_entries.async_update_entry(entry, options={'notify_destination':replacement,'notify_errors':True})
            release.set()
            await task
    assert delivered == ['qa_new'], 'changed recipient and disable must take effect before delivery'
    assert await hass.config_entries.async_unload(entry.entry_id)
