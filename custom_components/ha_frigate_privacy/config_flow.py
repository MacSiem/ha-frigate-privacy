"""Config flow for Frigate Privacy."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries

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
