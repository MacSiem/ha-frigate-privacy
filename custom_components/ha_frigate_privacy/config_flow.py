"""Config flow for Frigate Privacy."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN


class FrigatePrivacyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single-instance setup flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="Frigate Privacy", data={})

        return self.async_show_form(step_id="user", data_schema=None)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FrigatePrivacyOptionsFlow()


def notification_destinations(hass):
    """Only available HA notification actions or notify entities are selectable."""
    values = {'': 'Disabled', 'persistent_notification.create': 'Home Assistant'}
    for service in hass.services.async_services().get('notify', {}):
        if service not in {'reload', 'send_message'}:
            values['notify.' + service] = 'notify.' + service
    if hass.services.has_service('notify', 'send_message'):
        for state in hass.states.async_all('notify'):
            if state.state != 'unavailable':
                values['entity:' + state.entity_id] = state.name
    return values


class FrigatePrivacyOptionsFlow(config_entries.OptionsFlow):
    """Optional notifications and explicitly trusted HA action sources."""
    async def async_step_init(self, user_input=None):
        import voluptuous as vol
        from homeassistant.helpers import selector
        destinations = notification_destinations(self.hass)
        errors = {}
        if user_input is not None:
            if user_input.get('notify_destination', '') not in destinations:
                errors['notify_destination'] = 'invalid_destination'
            elif any(not isinstance(value, str) or not value.startswith(('automation.', 'script.'))
                     for value in user_input.get('trusted_actions', [])):
                errors['trusted_actions'] = 'invalid_action'
            else:
                return self.async_create_entry(title='', data=user_input)
        options = {**self.config_entry.options, **(user_input or {})}
        return self.async_show_form(step_id='init', errors=errors, data_schema=vol.Schema({
            vol.Required('notify_destination', default=options.get('notify_destination', '')): selector.SelectSelector(selector.SelectSelectorConfig(
                options=[{'value':value, 'label':label} for value,label in destinations.items()], mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required('notify_errors', default=options.get('notify_errors', True)): bool,
            vol.Required('notify_paused', default=options.get('notify_paused', False)): bool,
            vol.Required('notify_resumed', default=options.get('notify_resumed', False)): bool,
            vol.Required('notify_scheduled', default=options.get('notify_scheduled', False)): bool,
            vol.Optional('trusted_actions', default=options.get('trusted_actions', [])): selector.EntitySelector(selector.EntitySelectorConfig(domain=['automation','script'], multiple=True)),
        }))
