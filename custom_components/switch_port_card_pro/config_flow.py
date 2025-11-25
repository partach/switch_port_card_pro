"""Config Flow for Switch Port Card Pro."""

from __future__ import annotations

from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    CONF_PORTS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COMMUNITY, default="public"): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_PORTS, default=DEFAULT_PORTS): vol.All(
            vol.Coerce(list), [vol.Range(min=1, max=128)]
        ),
        vol.Optional("oid_rx", default=DEFAULT_BASE_OIDS["rx"]): str,
        vol.Optional("oid_tx", default=DEFAULT_BASE_OIDS["tx"]): str,
        vol.Optional("oid_status", default=DEFAULT_BASE_OIDS["status"]): str,
        vol.Optional("oid_speed", default=DEFAULT_BASE_OIDS["speed"]): str,
        vol.Optional("oid_name", default=DEFAULT_BASE_OIDS.get("name", "")): str,
        vol.Optional("oid_cpu", default=DEFAULT_SYSTEM_OIDS.get("cpu_zyxel", "")): str,
        vol.Optional("oid_memory", default=DEFAULT_SYSTEM_OIDS.get("memory_zyxel", "")): str,
        vol.Optional("oid_hostname", default=DEFAULT_SYSTEM_OIDS.get("hostname", "")): str,
    }
)


class SwitchPortCardProConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Main config flow for Switch Port Card Pro."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step – add integration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Set unique ID to prevent duplicates
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            # Optional: Test SNMP connectivity here
            # if not await self._test_snmp_connection(user_input):
            #     errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_COMMUNITY: user_input[CONF_COMMUNITY],
                    },
                    options={
                        CONF_PORTS: DEFAULT_PORTS,
                        "oid_rx": DEFAULT_BASE_OIDS["rx"],
                        "oid_tx": DEFAULT_BASE_OIDS["tx"],
                        "oid_status": DEFAULT_BASE_OIDS["status"],
                        "oid_speed": DEFAULT_BASE_OIDS["speed"],
                        "oid_name": DEFAULT_BASE_OIDS.get("name", ""),
                        "oid_cpu": DEFAULT_SYSTEM_OIDS.get("cpu_zyxel", ""),
                        "oid_memory": DEFAULT_SYSTEM_OIDS.get("memory_zyxel", ""),
                        "oid_hostname": DEFAULT_SYSTEM_OIDS.get("hostname", ""),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"name": "Switch Port Card Pro"},
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow."""
        return SwitchPortCardProOptionsFlow(config_entry)


class SwitchPortCardProOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Switch Port Card Pro."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return await self.async_step_options(user_input)

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Pre-fill with current options
        current_options = self.config_entry.options
        
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PORTS,
                    default=current_options.get(CONF_PORTS, DEFAULT_PORTS),
                ): cv.multi_select(
                    {str(i): str(i) for i in range(1, 129)}
                ),
                vol.Optional(
                    "oid_rx",
                    default=current_options.get("oid_rx", DEFAULT_BASE_OIDS["rx"]),
                ): str,
                vol.Optional(
                    "oid_tx",
                    default=current_options.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
                ): str,
                vol.Optional(
                    "oid_status",
                    default=current_options.get("oid_status", DEFAULT_BASE_OIDS["status"]),
                ): str,
                vol.Optional(
                    "oid_speed",
                    default=current_options.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
                ): str,
                vol.Optional(
                    "oid_name",
                    default=current_options.get("oid_name", DEFAULT_BASE_OIDS.get("name", "")),
                ): str,
                vol.Optional(
                    "oid_cpu",
                    default=current_options.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu_zyxel", "")),
                ): str,
                vol.Optional(
                    "oid_memory",
                    default=current_options.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory_zyxel", "")),
                ): str,
                vol.Optional(
                    "oid_hostname",
                    default=current_options.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=schema,
            description_placeholders={"name": self.config_entry.title},
        )
