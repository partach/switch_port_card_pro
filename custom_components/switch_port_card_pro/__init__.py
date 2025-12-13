"""Switch Port Card Pro integration - __init__.py"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from .sensor import SwitchPortCoordinator
import asyncio

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_COMMUNITY,
    CONF_PORTS,
    CONF_INCLUDE_VLANS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
)
_LOGGER = logging.getLogger(__name__)

# Required for config-flow-only integrations
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (YAML path unused but required)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Switch Port Card Pro from a config entry."""

    # Just ensure the domain data structure exists
    hass.data.setdefault(DOMAIN, {})

    entry.async_on_unload(entry.add_update_listener(async_options_updated))

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
    
async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when options are changed — force full reload."""
    await hass.config_entries.async_reload(entry.entry_id)
