"""Switch Port Card Pro integration - __init__.py"""

from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_validation import config_entry_only_config_schema
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = config_entry_only_config_schema("switch_port_card_pro")

PLATFORMS = [Platform.SENSOR]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    # Nothing needed here — platform loading handled by HA using manifest.json
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # No platform forwarding → nothing to unload manually
    return True
