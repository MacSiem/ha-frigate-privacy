"""Native options flow and explicit delegation policy."""
import pytest
from homeassistant.data_entry_flow import InvalidData
from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.exceptions import Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.ha_frigate_privacy.const import DOMAIN
from custom_components.ha_frigate_privacy import _async_require_admin

async def test_native_options_save_notification_preferences(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow['type'] == 'form'
    result = await hass.config_entries.options.async_configure(flow['flow_id'], {
        'notify_destination': 'persistent_notification.create',
        'notify_errors': True, 'notify_paused': False, 'notify_resumed': True,
        'trusted_actions': [],
    })
    assert result['type'] == 'create_entry'
    assert entry.options['notify_destination'] == 'persistent_notification.create'
    assert entry.options['notify_resumed'] is True

async def test_options_reject_unavailable_notification_destination(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(flow['flow_id'], {
            'notify_destination': 'shell_command.execute',
            'notify_errors': True, 'notify_paused': False, 'notify_resumed': False,
            'trusted_actions': [],
        })
    assert entry.options == {}, 'invalid destination must not be persisted'

async def test_system_context_requires_a_current_registered_trusted_action(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN,
                            options={'trusted_actions': ['automation.privacy_button']})
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {'config_entry': entry}
    context = Context()
    hass.states.async_set('automation.privacy_button', 'on', context=context)
    call = ServiceCall(DOMAIN, 'pause_camera', {}, context=context)
    try:
        await _async_require_admin(hass, call)
    except Unauthorized:
        pass
    else:
        raise AssertionError('A REST/state-only automation must not grant authority')

async def test_explicit_trusted_automation_can_call_with_its_real_context(hass: HomeAssistant):
    from homeassistant.setup import async_setup_component
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN,
                            options={'trusted_actions': ['automation.privacy_button']})
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {'config_entry': entry}
    accepted = []
    async def probe(call):
        await _async_require_admin(hass, call)
        accepted.append(call.context.user_id)
    hass.services.async_register(DOMAIN, 'probe', probe)
    assert await async_setup_component(hass, 'automation', {'automation': [{
        'id': 'privacy-button-test', 'alias': 'Privacy button',
        'trigger': [{'platform': 'event', 'event_type': 'qa_privacy_press'}],
        'action': [{'service': DOMAIN + '.probe'}],
    }]})
    await hass.async_block_till_done()
    hass.bus.async_fire('qa_privacy_press')
    await hass.async_block_till_done()
    assert accepted == [None], 'explicitly trusted physical-event automation must work without a user account'
    hass.config_entries.async_update_entry(entry, options={'trusted_actions': []})
    hass.bus.async_fire('qa_privacy_press')
    await hass.async_block_till_done()
    assert accepted == [None], 'revoking trust must stop the next automation action'

async def test_explicit_trusted_script_can_run_without_a_user_session(hass: HomeAssistant):
    from homeassistant.setup import async_setup_component
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN,
                            options={'trusted_actions': ['script.privacy_button']})
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {'config_entry': entry}
    accepted = []
    async def probe(call):
        await _async_require_admin(hass, call)
        accepted.append(call.context.user_id)
    hass.services.async_register(DOMAIN, 'probe', probe)
    assert await async_setup_component(hass, 'script', {'script': {
        'privacy_button': {'sequence': [{'service': DOMAIN + '.probe'}]},
    }})
    await hass.async_block_till_done()
    await hass.services.async_call('script', 'privacy_button', {}, blocking=True)
    await hass.async_block_till_done()
    assert accepted == [None]
