import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.config_entries import ConfigEntry

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

# --- Initial setup schema ---
SETUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COMMUNITY): str,
    }
)


def build_options_schema(current: dict[str, Any]) -> vol.Schema:
    """Create options form dynamically using current values."""

    def get_oid_default(key: str, defaults: dict) -> str:
        nested = current.get(CONF_BASE_OIDS, {})
        return nested.get(key, defaults.get(key))

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

            vol.Optional(CONF_BASE_OIDS): vol.Schema(
                {
                    # Port OIDs
                    vol.Optional("rx", default=get_oid_default("rx", DEFAULT_BASE_OIDS)): str,
                    vol.Optional("tx", default=get_oid_default("tx", DEFAULT_BASE_OIDS)): str,
                    vol.Optional("status", default=get_oid_default("status", DEFAULT_BASE_OIDS)): str,
                    vol.Optional("speed", default=get_oid_default("speed", DEFAULT_BASE_OIDS)): str,
                    vol.Optional("name", default=get_oid_default("name", DEFAULT_BASE_OIDS)): str,
                    vol.Optional("vlan", default=get_oid_default("vlan", DEFAULT_BASE_OIDS)): str,

                    # System OIDs
                    vol.Optional("cpu", default=get_oid_default("cpu", DEFAULT_SYSTEM_OIDS)): str,
                    vol.Optional("cpu_zyxel", default=get_oid_default("cpu_zyxel", DEFAULT_SYSTEM_OIDS)): str,
                    vol.Optional("memory", default=get_oid_default("memory", DEFAULT_SYSTEM_OIDS)): str,
                    vol.Optional("memory_zyxel", default=get_oid_default("memory_zyxel", DEFAULT_SYSTEM_OIDS)): str,
                    vol.Optional("uptime", default=get_oid_default("uptime", DEFAULT_SYSTEM_OIDS)): str,
                    vol.Optional("hostname", default=get_oid_default("hostname", DEFAULT_SYSTEM_OIDS)): str,
                }
            ),
        }
    )


class SwitchPortCardProConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry):
        return SwitchPortCardProOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
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
                _LOGGER.exception("Unexpected error")
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

    async def _test_connection(self, hass: HomeAssistant, host: str, community: str):
        await async_snmp_get(hass, host, community, "1.3.6.1.2.1.1.5.0")


class SwitchPortCardProOptionsFlowHandler(config_entries.OptionsFlow):
    """Options handler."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
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
