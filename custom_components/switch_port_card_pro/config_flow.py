"""Config Flow for Switch Port Card Pro."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import homeassistant.helpers.selector as selector
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.core import callback

from .snmp_helper import async_snmp_get 
from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    CONF_PORTS,
    CONF_INCLUDE_VLANS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
    CONF_SFP_PORTS_START,
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
    #                    CONF_PORTS: DEFAULT_PORTS, # removed for auto port detection
                        CONF_INCLUDE_VLANS: False,
                        "snmp_version": "v2c",
                        "oid_rx": DEFAULT_BASE_OIDS["rx"],
                        "oid_tx": DEFAULT_BASE_OIDS["tx"],
                        "oid_status": DEFAULT_BASE_OIDS["status"],
                        "oid_speed": DEFAULT_BASE_OIDS["speed"],
                        "oid_name": DEFAULT_BASE_OIDS.get("name", ""),
                        "oid_vlan": DEFAULT_BASE_OIDS.get("vlan", ""),
                        "oid_cpu": DEFAULT_SYSTEM_OIDS.get("cpu", ""),
                        "firmware": DEFAULT_SYSTEM_OIDS.get("firmware", ""),
                        "oid_memory": DEFAULT_SYSTEM_OIDS.get("memory", ""),
                        "oid_hostname": DEFAULT_SYSTEM_OIDS.get("hostname", ""),
                        "oid_uptime": DEFAULT_SYSTEM_OIDS.get("uptime", ""),
                        "oid_poe_power": DEFAULT_SYSTEM_OIDS.get("poe_power", ""),
                        "oid_poe_status": DEFAULT_SYSTEM_OIDS.get("poe_status", ""),
                        "oid_custom": DEFAULT_SYSTEM_OIDS.get("oid_custom", ""),
                        "update_interval": 20,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, hass: HomeAssistant, host: str, community: str) -> None:
      """SNMP connectivity test direct await, no executor nonsense."""
      await async_snmp_get(
        hass,
        host,
        community,
        "1.3.6.1.2.1.1.5.0",   # sysName — more reliable than sysDescr
        timeout=12,
        retries=3,
        mp_model=1,            # v2c
      )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Return options flow."""
        return SwitchPortCardProOptionsFlow(config_entry)


class SwitchPortCardProOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Switch Port Card Pro."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize."""
    #    self.config_entry = config_entry # depricated in HA 2025.12

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
            

            try:
                new = {**current, **user_input}
                return self.async_create_entry(title="", data=new)
            except Exception as err:
                _LOGGER.exception("Error saving options: %s", err)
                return self.async_abort(reason="Error storing input")            

        # Prepare for schema generation
        ports_dict = {str(i): str(i) for i in range(1, 65)}
        current_ports = [str(p) for p in current.get(CONF_PORTS, DEFAULT_PORTS)]

        # --- Options Schema ---
        schema = vol.Schema(
            {
                vol.Optional(
                    "update_interval",
                    default=current.get("update_interval", 20)
                ): cv.positive_int,
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
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="RX OID for RX Counter",
                        subtitle="Will be use in live RX calculation",
                        )
                ),
                vol.Optional(
                    "oid_tx",
                    default=current.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="TX OID for TX Counter",
                        subtitle="Will be use in live TX calculation",
                        )
                ),
                vol.Optional(
                    "oid_status",
                    default=current.get("oid_status", DEFAULT_BASE_OIDS["status"]),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Port Status OID",
                        subtitle="To determine port on/off",
                        )
                ),
                vol.Optional(
                    "oid_speed",
                    default=current.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Port Speed OID",
                        subtitle="To determine port speed (10M/100M/1G/...)",
                        )
                ),
                vol.Optional(
                    "oid_name",
                    default=current.get("oid_name", DEFAULT_BASE_OIDS.get("name", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Port Name OID",
                        subtitle="To user given name of the port in switch config",
                        )
                ),
                vol.Optional(
                    "oid_vlan",
                    default=current.get("oid_vlan", DEFAULT_BASE_OIDS.get("vlan", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Port Vlan OID",
                        subtitle="To determine Vlan ID of port",
                        )
                ),

                # --- System OIDs ---
                vol.Optional(
                    "oid_cpu",
                    default=current.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="CPU load percentage OID",
                        subtitle="Must be return percentage value",
                        )
                ),
                vol.Optional(
                    "oid_firmware",
                    default=current.get("oid_firmware", DEFAULT_SYSTEM_OIDS.get("firmware", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Firmware version string OID",
                        subtitle="Retrieved text is used directly",
                        )
                ),
                vol.Optional(
                    "oid_memory",
                    default=current.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Memory load percentage OID",
                        subtitle="Must be return percentage value",
                        )
                ),
                vol.Optional(
                    "oid_hostname",
                    default=current.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Switch name/type OID",
                        subtitle="Retrieved text is used directly",
                        )
                ),
                vol.Optional(
                    "oid_uptime",
                    default=current.get("oid_uptime", DEFAULT_SYSTEM_OIDS.get("uptime", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Up time OID",
                        subtitle="Time in seconds is translated to D:H:M",
                        )
                ),
                vol.Optional(
                    "oid_poe_power",
                    default=current.get("oid_poe_power", DEFAULT_SYSTEM_OIDS.get("poe_power", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="POE Port Power OID",
                        subtitle="POE power for port is required",
                        )
                ),
                vol.Optional(
                    "oid_poe_status",
                    default=current.get("oid_poe_status", DEFAULT_SYSTEM_OIDS.get("poe_status", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="POE Port Status OID",
                        subtitle="POE status retrieval per port",
                        )
                ),
                vol.Optional(
                    "oid_custom",
                    default=current.get("oid_custom", DEFAULT_SYSTEM_OIDS.get("oid_custom", "")),
                ): selector.TextSelector(selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        title="Custom OID",
                        subtitle="Result of retrieving this OID will be directly displayed in the system part of the card",
                        )
                ),
                vol.Optional(
                    "snmp_version",
                    default=current.get("snmp_version", "v2c"),
                ): vol.In({"v2c": "v2c", "v1": "v1"}),
 #               vol.Optional(
 #                   CONF_SFP_PORTS_START, default=25 # for a 24 port switch
 #               ): vol.All(vol.Coerce(int), vol.Range(min=1, max=52)),
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=schema,
        )
