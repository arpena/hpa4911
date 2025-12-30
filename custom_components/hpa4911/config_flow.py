"""Config flow for Local BGH Smart integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS, CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_MAC): cv.string,
        vol.Optional(CONF_IP_ADDRESS): cv.string,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Local BGH Smart."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate MAC address format
            mac = user_input[CONF_MAC].upper().replace("-", ":")
            if not self._is_valid_mac(mac):
                errors[CONF_MAC] = "invalid_mac"
            else:
                # Create unique ID from MAC address
                await self.async_set_unique_id(mac.replace(":", ""))
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_MAC: mac,
                        CONF_IP_ADDRESS: user_input.get(CONF_IP_ADDRESS),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    def _is_valid_mac(self, mac: str) -> bool:
        """Validate MAC address format."""
        import re
        return bool(re.match(r"^([0-9A-F]{2}[:]){5}([0-9A-F]{2})$", mac))
