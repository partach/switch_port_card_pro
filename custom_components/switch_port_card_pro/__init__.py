"""Switch Port Card Pro integration - __init__.py"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from datetime import timedelta
from homeassistant.helpers import config_validation as cv
from .sensor import SwitchPortCoordinator
#import asyncio
from .snmp_helper import (
    discover_physical_ports,
)

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_COMMUNITY,
    CONF_PORTS,
    CONF_INCLUDE_VLANS,
    SNMP_VERSION_TO_MP_MODEL,
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
    community = entry.data[CONF_COMMUNITY]
    update_seconds = max(3, entry.options.get("update_interval", 20))
    include_vlans = entry.options.get(CONF_INCLUDE_VLANS, True)
    snmp_version = entry.options.get("snmp_version", "v2c")
    mp_model = SNMP_VERSION_TO_MP_MODEL.get(snmp_version, 1)

    # === AUTO-DETECT PORTS + FIRST-INSTALL AUTO-CONFIG ===
    # Skip full discovery if already installed successfully
    install_complete = entry.options.get("install_complete", False)
    detected = None
    if not install_complete:
        # First-time: run discovery
        try:
            detected = await discover_physical_ports(hass, host, community, mp_model)
            if detected:
                all_ports = sorted(int(p) for p in detected.keys())

                new_options = dict(entry.options)
                new_options[CONF_PORTS] = list(range(1, len(all_ports) + 1))

                sfp_ports = [p for p, info in detected.items() if info.get("is_sfp")]
                if sfp_ports:
                    new_options["sfp_ports_start"] = min(sfp_ports)

                # Update options (but don't set install_complete here — do at end)
                hass.config_entries.async_update_entry(entry, options=new_options)
                _LOGGER.info("First install: auto-configured %d ports on %s (SFP starts at %s)", len(all_ports), host, new_options.get("sfp_ports_start", "none"))

                ports = all_ports.copy()
            else:
                ports = list(range(1, 9))
                _LOGGER.warning("Port auto-detection failed on %s → falling back to 8 ports", host)
        except Exception as err:
            ports = list(range(1, 9))
            _LOGGER.error("Error during port auto-detection: %s", err)
    else:
        # Already installed — trust saved config
        ports = entry.options.get(CONF_PORTS, list(range(1, 9)))
        _LOGGER.debug("Integration already configured — skipping port discovery on %s", host)

    # Build OID sets
    base_oids = {
        "rx": entry.options.get("oid_rx", DEFAULT_BASE_OIDS["rx"]),
        "tx": entry.options.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
        "status": entry.options.get("oid_status", DEFAULT_BASE_OIDS["status"]),
        "speed": entry.options.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
        "name": entry.options.get("oid_name", DEFAULT_BASE_OIDS.get("name", "")),
        "vlan": entry.options.get("oid_vlan", DEFAULT_BASE_OIDS.get("vlan", "")),
        "poe_power": entry.options.get("oid_poe_power", DEFAULT_BASE_OIDS.get("poe_power", "")),
        "poe_status": entry.options.get("oid_poe_status", DEFAULT_BASE_OIDS.get("poe_status", "")),
        "port_custom": entry.options.get("oid_port_custom", DEFAULT_BASE_OIDS.get("port_custom", "")),
    }

    system_oids = {
        "cpu": entry.options.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu", "")),
        "memory": entry.options.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory", "")),
        "firmware": entry.options.get("oid_firmware", DEFAULT_BASE_OIDS.get("firmware", "")),
        "hostname": entry.options.get("oid_hostname", DEFAULT_BASE_OIDS.get("hostname", "")),
        "uptime": entry.options.get("oid_uptime", DEFAULT_BASE_OIDS.get("uptime", "")),
        "poe_total": entry.options.get("oid_poe_total", DEFAULT_BASE_OIDS.get("poe_total", "")),
        "custom": entry.options.get("oid_custom", DEFAULT_BASE_OIDS.get("custom", "")),
    }

    # Create coordinator
    coordinator = SwitchPortCoordinator(
        hass, host, community, ports, base_oids, system_oids, snmp_version, include_vlans, update_seconds
    )
    coordinator.device_name = entry.title
    coordinator.port_mapping = detected or {}
    coordinator.config_entry = entry  # For flag check in coordinator
    coordinator.update_interval = timedelta(seconds=update_seconds)


    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward to platforms (fast — no blocking)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Mark as successfully installed (only if we reached here)
    if not entry.options.get("install_complete", False):
        new_options = dict(entry.options)
        new_options["install_complete"] = True
        hass.config_entries.async_update_entry(entry, options=new_options)
        _LOGGER.info("Switch Port Card Pro integration successfully installed on %s", host)

    # Background first refresh
    hass.loop.create_task(coordinator.async_refresh())

    entry.async_on_unload(entry.add_update_listener(async_options_updated))

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
