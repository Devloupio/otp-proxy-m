"""Config flow to set up an OTP Proxy M entry."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import CONF_UPSTREAM, DEFAULT_UPSTREAM, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="OTP Proxy M"): str,
        vol.Required(CONF_UPSTREAM, default=DEFAULT_UPSTREAM): str,
        vol.Required("route_key", default="m"): str,
    }
)


class OtpProxyMFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OTP Proxy M."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input["route_key"])
            self._abort_if_unique_id_mismatch()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OtpProxyMOptionsFlow(config_entry)


class OtpProxyMOptionsFlow(config_entries.OptionsFlow):
    """Handle options (change upstream URL / route key)."""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPSTREAM,
                        default=self.config_entry.data.get(CONF_UPSTREAM, DEFAULT_UPSTREAM),
                    ): str,
                }
            ),
        )
