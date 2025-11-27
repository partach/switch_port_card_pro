"""Config Flow for Switch Port Card Pro."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .snmp_helper import async_snmp_get 
from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    CONF_PORTS,
    CONF_INCLUDE_VLANS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
)

_LOGGER = logging.getLogger(__name__)

# --- Initial setup schema ---
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COMMUNITY, default="public"): str,
    }
)


class SwitchPortCardProConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Switch Port Card Pro."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST].lower())
            self._abort_if_unique_id_configured()

            # Connection Test: Crucial for network integrations
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
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"

            if not errors:
                # Create entry with data and initial default options
                return self.async_create_entry(
                    title=user_input[CONF_HOST],
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_COMMUNITY: user_input[CONF_COMMUNITY],
                    },
                    options={
                        CONF_PORTS: DEFAULT_PORTS,
                        CONF_INCLUDE_VLANS: False,
                        "snmp_version": "v2c",
                        "oid_rx": DEFAULT_BASE_OIDS["rx"],
                        "oid_tx": DEFAULT_BASE_OIDS["tx"],
                        "oid_status": DEFAULT_BASE_OIDS["status"],
                        "oid_speed": DEFAULT_BASE_OIDS["speed"],
                        "oid_name": DEFAULT_BASE_OIDS.get("name", ""),
                        "oid_vlan": DEFAULT_BASE_OIDS.get("vlan", ""),
                        "oid_cpu": DEFAULT_SYSTEM_OIDS.get("cpu", ""),
                        "oid_cpu_zyxel": DEFAULT_SYSTEM_OIDS.get("cpu_zyxel", ""),
                        "oid_memory": DEFAULT_SYSTEM_OIDS.get("memory", ""),
                        "oid_memory_zyxel": DEFAULT_SYSTEM_OIDS.get("memory_zyxel", ""),
                        "oid_hostname": DEFAULT_SYSTEM_OIDS.get("hostname", ""),
                        "oid_uptime": DEFAULT_SYSTEM_OIDS.get("uptime", ""),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, hass: HomeAssistant, host: str, community: str) -> None:
        """SNMP connectivity test with generous timeout for config flow."""
        await self.hass.async_add_executor_job(
            async_snmp_get, # Pass the function reference
            self.hass,      # First argument: hass
            host,           # Second argument: host
            community,      # Third argument: community
            "1.3.6.1.2.1.1.1.0",
            timeout=10,
            retries=2,
            mp_model=(0 if snmp_version == "v1" else 1),
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry):
        """Return options flow."""
        return SwitchPortCardProOptionsFlow(config_entry)


class SwitchPortCardProOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Switch Port Card Pro."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return await self.async_step_options(user_input)

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options."""
        current = self.config_entry.options

        if user_input is not None:
            # Convert port strings (from multi-select) to integers for saving
            if CONF_PORTS in user_input and isinstance(user_input[CONF_PORTS], list):
                user_input[CONF_PORTS] = [int(p) for p in user_input[CONF_PORTS]]
            
            # FIX: Use options=user_input to update options, and data=None to protect the main config.
            return self.async_create_entry(title="", data=None, options=user_input)

        # Prepare for schema generation
        ports_dict = {str(i): str(i) for i in range(1, 65)}
        current_ports = [str(p) for p in current.get(CONF_PORTS, DEFAULT_PORTS)]

        # --- Options Schema ---
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PORTS,
                    default=current_ports,
                ): cv.multi_select(ports_dict),
                
                vol.Optional(
                    CONF_INCLUDE_VLANS,
                    default=current.get(CONF_INCLUDE_VLANS, False),
                ): cv.boolean,
                
                # --- Port OIDs ---
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
                    "oid_vlan",
                    default=current.get("oid_vlan", DEFAULT_BASE_OIDS.get("vlan", "")),
                ): str,

                # --- System OIDs ---
                vol.Optional(
                    "oid_cpu",
                    default=current.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu", "")),
                ): str,
                vol.Optional(
                    "oid_cpu_zyxel",
                    default=current.get("oid_cpu_zyxel", DEFAULT_SYSTEM_OIDS.get("cpu_zyxel", "")),
                ): str,
                vol.Optional(
                    "oid_memory",
                    default=current.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory", "")),
                ): str,
                vol.Optional(
                    "oid_memory_zyxel",
                    default=current.get("oid_memory_zyxel", DEFAULT_SYSTEM_OIDS.get("memory_zyxel", "")),
                ): str,
                vol.Optional(
                    "oid_hostname",
                    default=current.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
                ): str,
                vol.Optional(
                    "oid_uptime",
                    default=current.get("oid_uptime", DEFAULT_SYSTEM_OIDS.get("uptime", "")),
                ): str,
                vol.Optional(
                    "snmp_version",
                    default=current.get("snmp_version", "v2c"),
                ): vol.In({"v2c": "v2c", "v1": "v1"}),
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=schema,
        )
