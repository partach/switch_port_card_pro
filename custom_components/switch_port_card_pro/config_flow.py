import logging
from typing import Any, List

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv

# Import constants from const.py
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

# --- Configuration Schemas ---

# Schema for initial setup (Host and Community)
SETUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COMMUNITY): str,
    }
)

# Schema for the Advanced Options Flow
OPTIONS_SCHEMA = vol.Schema(
    {
        # Port Configuration
        vol.Optional(
            CONF_PORTS, 
            default=",".join(map(str, DEFAULT_PORTS))
        ): str, # Stored as a comma-separated string
        vol.Optional(
            CONF_INCLUDE_VLANS, 
            default=False
        ): cv.boolean,

        # OID Overrides (Default OIDs are defined in const.py)
        vol.Optional(CONF_BASE_OIDS): vol.Schema(
            {
                # Port-level OIDs
                vol.Optional("rx", default=DEFAULT_BASE_OIDS["rx"]): str,
                vol.Optional("tx", default=DEFAULT_BASE_OIDS["tx"]): str,
                vol.Optional("status", default=DEFAULT_BASE_OIDS["status"]): str,
                vol.Optional("speed", default=DEFAULT_BASE_OIDS["speed"]): str,
                vol.Optional("name", default=DEFAULT_BASE_OIDS["name"]): str,
                vol.Optional("vlan", default=DEFAULT_BASE_OIDS["vlan"]): str,

                # System-level OIDs
                vol.Optional("cpu", default=DEFAULT_SYSTEM_OIDS["cpu"]): str,
                vol.Optional("cpu_zyxel", default=DEFAULT_SYSTEM_OIDS["cpu_zyxel"]): str,
                vol.Optional("memory", default=DEFAULT_SYSTEM_OIDS["memory"]): str,
                vol.Optional("memory_zyxel", default=DEFAULT_SYSTEM_OIDS["memory_zyxel"]): str,
                vol.Optional("uptime", default=DEFAULT_SYSTEM_OIDS["uptime"]): str,
                vol.Optional("hostname", default=DEFAULT_SYSTEM_OIDS["hostname"]): str,
            }
        ),
    }
)

# --- Main Config Flow ---

class SwitchPortCardProConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Switch Port Card Pro."""

    VERSION = 1
    
    # 1. Link the Options Flow Handler
    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return SwitchPortCardProOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            # Check if this host is already configured
            await self.async_set_unique_id(user_input[CONF_HOST].lower())
            self._abort_if_unique_id_configured()

            # 2. Connection Validation (Placeholder for actual SNMP check)
            try:
                await self._test_connection(user_input[CONF_HOST], user_input[CONF_COMMUNITY])
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception: # Catch all other errors during connection test
                errors["base"] = "unknown"

            if not errors:
                # Setup is successful, create the entry.
                # All advanced settings will use the default values set in OPTIONS_SCHEMA
                # unless changed by the user in the Options Flow later.
                return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)

        # Show the initial configuration form
        return self.async_show_form(
            step_id="user",
            data_schema=SETUP_SCHEMA,
            errors=errors,
        )

    # Placeholder for a real connection test
    async def _test_connection(self, host: str, community: str) -> None:
        """Test if we can connect to the SNMP host."""
        _LOGGER.debug("Testing SNMP connection to %s with community %s", host, community)
        # In a real integration, this would use the SNMP library 
        # to perform a simple GET (e.g., sysName) and raise a 
        # ConnectionError if it fails.
        if host == "fail_host": # Example failure case
             raise ConnectionError("Host failed to respond to SNMP.")


# --- Options Flow ---

class SwitchPortCardProOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Switch Port Card Pro."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the options flow."""
        
        if user_input is not None:
            # 3. CORRECT WAY TO SAVE OPTIONS:
            # Use self.async_create_entry to update the 'options' of the config entry
            return self.async_create_entry(title="", data=user_input)
        
        # Determine the current state of options (use existing options or main data defaults)
        # This allows the form to be pre-filled with the current settings.
        options = {
            # Start with existing options, if any, falling back to main data or defaults.
            **OPTIONS_SCHEMA({}), 
            **self.config_entry.options, 
        }

        # Show the advanced options form
        return self.async_show_form(
            step_id="init",
            data_schema=OPTIONS_SCHEMA,
            description_placeholders={
                "base_oids_info": "Customize these OIDs if the automatic discovery or defaults do not work for your specific switch model."
            },
            # Pass current options to pre-fill the form
            initial_data=options,
        )
