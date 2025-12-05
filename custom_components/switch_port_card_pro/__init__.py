"""Switch Port Card Pro integration - __init__.py"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from .sensor import SwitchPortCoordinator

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

    hass.data[DOMAIN].pop(entry.entry_id, None)
    
    host = entry.data[CONF_HOST]
    update_seconds = entry.options.get("update_interval", 20)
    community = entry.data[CONF_COMMUNITY]
    ports = entry.options.get(CONF_PORTS, DEFAULT_PORTS)
    include_vlans = entry.options.get(CONF_INCLUDE_VLANS, True)
    snmp_version = entry.options.get("snmp_version", "v2c")

    base_oids = {
        "rx": entry.options.get("oid_rx", DEFAULT_BASE_OIDS["rx"]),
        "tx": entry.options.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
        "status": entry.options.get("oid_status", DEFAULT_BASE_OIDS["status"]),
        "speed": entry.options.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
        "name": entry.options.get("oid_name", DEFAULT_BASE_OIDS.get("name", "")),
        "vlan": entry.options.get("oid_vlan", DEFAULT_BASE_OIDS.get("vlan", "")),
        "poe_power": entry.options.get("oid_poe_power", DEFAULT_BASE_OIDS.get("poe_power", "")),
        "poe_status": entry.options.get("oid_poe_status", DEFAULT_BASE_OIDS.get("poe_status", "")),
    }

    system_oids = {
        "cpu": entry.options.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu", "")),
        "memory": entry.options.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory", "")),
        "firmware": entry.options.get("oid_firmware", DEFAULT_SYSTEM_OIDS.get("firmware", "")),
        "hostname": entry.options.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
        "uptime": entry.options.get("oid_uptime", DEFAULT_SYSTEM_OIDS.get("uptime", "")),
        "poe_total": entry.options.get("oid_poe_total", DEFAULT_SYSTEM_OIDS.get("poe_total", "")),
    }

    coordinator = SwitchPortCoordinator(
        hass, host, community, ports, base_oids, system_oids, snmp_version, include_vlans, update_seconds
    )

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # First refresh
    await coordinator.async_config_entry_first_refresh()

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
