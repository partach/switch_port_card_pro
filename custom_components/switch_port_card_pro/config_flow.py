"""Config Flow for Switch Port Card Pro with full Options Flow."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST, CONF_NAME

from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    CONF_PORTS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
)

# ──────────────────────────────────────────────
# Initial setup schema (minimal — only what’s needed to connect)
# ──────────────────────────────────────────────
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COMMUNITY, default="public"): str,
    }
)

# ──────────────────────────────────────────────
# Full options schema (shown when user clicks "Configure")
# ──────────────────────────────────────────────
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_PORTS, default=DEFAULT_PORTS): vol.All(
            vol.Coerce(list), [vol.Range(min=1, max=128)]
        ),
        # ── Interface OIDs ───────────────────────
        vol.Optional("oid_rx", default=DEFAULT_BASE_OIDS["rx"]): str,
        vol.Optional("oid_tx", default=DEFAULT_BASE_OIDS["tx"]): str,
        vol.Optional("oid_status", default=DEFAULT_BASE_OIDS["status"]): str,
        vol.Optional("oid_speed", default=DEFAULT_BASE_OIDS["speed"]): str,
        vol.Optional("oid_name", default=DEFAULT_BASE_OIDS["name"]): str,
        # ── System OIDs ──────────────────────────
        vol.Optional("oid_cpu", default=DEFAULT_SYSTEM_OIDS["cpu_zyxel"]): str,
        vol.Optional("oid_memory", default=DEFAULT_SYSTEM_OIDS["memory_zyxel"]): str,
        vol.Optional("oid_hostname", default=DEFAULT_SYSTEM_OIDS["hostname"]): str,
        # ── Future features ──────────────────────
        vol.Optional("include_vlans", default=False): bool,
    }
)


class SwitchPortCardProFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Main config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — add integration."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={"name": "Switch Port Card Pro"},
            )

        # Prevent duplicate entries by host
        await self.async_set_unique_id(user_input[CONF_HOST])
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=user_input[CONF_HOST],
            data={
                CONF_HOST: user_input[CONF_HOST],
                CONF_COMMUNITY: user_input[CONF_COMMUNITY],
            },
            # Default options (will be overridable later)
            options={
                CONF_PORTS: DEFAULT_PORTS,
                "oid_rx": DEFAULT_BASE_OIDS["rx"],
                "oid_tx": DEFAULT_BASE_OIDS["tx"],
                "oid_status": DEFAULT_BASE_OIDS["status"],
                "oid_speed": DEFAULT_BASE_OIDS["speed"],
                "oid_name": DEFAULT_BASE_OIDS["name"],
                "oid_cpu": DEFAULT_SYSTEM_OIDS["cpu_zyxel"],
                "oid_memory": DEFAULT_SYSTEM_OIDS["memory_zyxel"],
                "oid_hostname": DEFAULT_SYSTEM_OIDS["hostname"],
                "include_vlans": False,
            },
        )

    # ──────────────────────────────────────────────
    # Options Flow — appears as "Configure" button
    # ──────────────────────────────────────────────
    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Pre-fill current options
        data_schema = self.add_suggested_values_to_schema(
            OPTIONS_SCHEMA, self.config_entry.options
        )

        return self.async_show_form(
            step_id="options",
            data_schema=data_schema,
            description_placeholders={"name": self.config_entry.title},
        )

    # Make "Configure" button appear
    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return SwitchPortCardProFlowOptions()


class SwitchPortCardProFlowOptions(config_entries.OptionsFlow):
    """Options flow handler (required for async_get_options_flow)."""

    def __init__(self):
        self.config_entry = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        self.config_entry = self.hass.config_entries.async_get_entry(
            self.handler  # handler == entry.entry_id
        )
        return await self.async_step_options(user_input)
