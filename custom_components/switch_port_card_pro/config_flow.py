"""Config Flow for Switch Port Card Pro."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
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


class SwitchPortCardProConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Main config flow for Switch Port Card Pro."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step add integration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

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
                        "oid_cpu": DEFAULT_SYSTEM_OIDS.get("cpu_switch", ""),
                        "oid_memory": DEFAULT_SYSTEM_OIDS.get("memory_switch", ""),
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

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options (entry point)."""
        return await self.async_step_options(user_input)

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            # Convert port strings to integers
            if CONF_PORTS in user_input:
                user_input[CONF_PORTS] = [int(p) for p in user_input[CONF_PORTS]]
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options

        # Build port selection list
        ports_dict = {str(i): str(i) for i in range(1, 65)}
        
        # Convert current ports to strings for display
        current_ports = [str(p) for p in current.get(CONF_PORTS, DEFAULT_PORTS)]

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PORTS,
                    default=current_ports,
                ): cv.multi_select(ports_dict),
                vol.Optional(
                    "oid_rx",
                    default=current.get("oid_rx", DEFAULT_BASE_OIDS["rx"]),
                ): str,
                vol.Optional(
                    "oid_tx",
                    default=current.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
                ): str,
                vol.Optional(
                    "oid_status",
                    default=current.get("oid_status", DEFAULT_BASE_OIDS["status"]),
                ): str,
                vol.Optional(
                    "oid_speed",
                    default=current.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
                ): str,
                vol.Optional(
                    "oid_name",
                    default=current.get("oid_name", DEFAULT_BASE_OIDS.get("name", "")),
                ): str,
                vol.Optional(
                    "oid_cpu",
                    default=current.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu_switch", "")),
                ): str,
                vol.Optional(
                    "oid_memory",
                    default=current.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory_switch", "")),
                ): str,
                vol.Optional(
                    "oid_hostname",
                    default=current.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=schema,
            description_placeholders={"name": self.config_entry.title},
        )
