"""Native options flow and explicit delegation policy."""
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
    result = await hass.config_entries.options.async_configure(flow['flow_id'], {
        'notify_destination': 'shell_command.execute',
        'notify_errors': True, 'notify_paused': False, 'notify_resumed': False,
        'trusted_actions': [],
    })
    assert result['type'] == 'form'
    assert result['errors'] == {'notify_destination': 'invalid_destination'}

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
