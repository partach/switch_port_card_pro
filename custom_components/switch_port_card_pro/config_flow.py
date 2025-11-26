import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .snmp_helper import async_snmp_get
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_COMMUNITY,
    CONF_PORTS,
    CONF_INCLUDE_VLANS,
    CONF_BASE_OIDS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
)

_LOGGER = logging.getLogger(__name__)

# Initial setup schema (host + community)
SETUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COMMUNITY): str,
    }
)


def build_options_schema(current: dict[str, Any]) -> vol.Schema:
    """Create options form dynamically using current values."""

    return vol.Schema(
        {
            vol.Optional(
                CONF_PORTS,
                default=current.get(
                    CONF_PORTS, ",".join(map(str, DEFAULT_PORTS))
                ),
            ): str,

            vol.Optional(
                CONF_INCLUDE_VLANS,
                default=current.get(CONF_INCLUDE_VLANS, False),
            ): cv.boolean,

            vol.Optional(CONF_BASE_OIDS, default=current.get(CONF_BASE_OIDS, {})): vol.Schema(
                {
                    vol.Optional("rx", default=current.get("rx", DEFAULT_BASE_OIDS["rx"])): str,
                    vol.Optional("tx", default=current.get("tx", DEFAULT_BASE_OIDS["tx"])): str,
                    vol.Optional("status", default=current.get("status", DEFAULT_BASE_OIDS["status"])): str,
                    vol.Optional("speed", default=current.get("speed", DEFAULT_BASE_OIDS["speed"])): str,
                    vol.Optional("name", default=current.get("name", DEFAULT_BASE_OIDS["name"])): str,
                    vol.Optional("vlan", default=current.get("vlan", DEFAULT_BASE_OIDS["vlan"])): str,

                    vol.Optional("cpu", default=current.get("cpu", DEFAULT_SYSTEM_OIDS["cpu"])): str,
                    vol.Optional("cpu_zyxel", default=current.get("cpu_zyxel", DEFAULT_SYSTEM_OIDS["cpu_zyxel"])): str,
                    vol.Optional("memory", default=current.get("memory", DEFAULT_SYSTEM_OIDS["memory"])): str,
                    vol.Optional("memory_zyxel", default=current.get("memory_zyxel", DEFAULT_SYSTEM_OIDS["memory_zyxel"])): str,
                    vol.Optional("uptime", default=current.get("uptime", DEFAULT_SYSTEM_OIDS["uptime"])): str,
                    vol.Optional("hostname", default=current.get("hostname", DEFAULT_SYSTEM_OIDS["hostname"])): str,
                }
            ),
        }
    )


class SwitchPortCardProConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Switch Port Card Pro."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return SwitchPortCardProOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Initial configuration step."""

        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST].lower())
            self._abort_if_unique_id_configured()

            try:
                await self._test_connection(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_COMMUNITY],
                )
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_community"
            except Exception:
                errors["base"] = "unknown"

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=SETUP_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, hass: HomeAssistant, host: str, community: str) -> None:
        """SNMP connectivity test."""
        await async_snmp_get(hass, host, community, "1.3.6.1.2.1.1.5.0")


class SwitchPortCardProOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Switch Port Card Pro."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle options."""

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {
            **self.config_entry.data,
            **self.config_entry.options,
        }

        return self.async_show_form(
            step_id="init",
            data_schema=build_options_schema(current),
        )
