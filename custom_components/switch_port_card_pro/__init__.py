"""Switch Port Card Pro integration - __init__.py"""
from __future__ import annotations

import logging
from pathlib import Path
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from datetime import timedelta
from homeassistant.helpers import config_validation as cv
from .sensor import SwitchPortCoordinator
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.frontend import add_extra_js_url
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


CARD_URL = "/switch-port-card-pro/switch-port-card-pro.js"
CARD_JS = "frontend/switch-port-card-pro.js"

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})

    try:
        js_file = Path(__file__).parent / CARD_JS

        # Safely check file existence (thread-safe)
        js_file_exists = await hass.async_add_executor_job(js_file.exists)

        if js_file_exists:
            await hass.http.async_register_static_paths([
                StaticPathConfig(CARD_URL, hass.config.path(CARD_JS))
            ])
            _LOGGER.info("Switch Port Card Pro card served at %s", CARD_JS)
        else:
            _LOGGER.warning("Frontend JS not found at %s card is not available", CARD_JS)

        add_extra_js_url(hass, CARD_URL)

    except Exception as err:
        _LOGGER.warning("Frontend registration failed for %s", CARD_JS)
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

    # === PORT DISCOVERY WITH SMART FALLBACK ===
    detected = None
    ports = None
    is_first_install = CONF_PORTS not in entry.options
    
    # Always TRY to detect ports (even if user configured manually)
    # This gives us interface names and SFP detection when it works
    try:
        detected = await discover_physical_ports(hass, host, community, mp_model)
        if detected:
            all_ports = sorted(int(p) for p in detected.keys())
            _LOGGER.debug("Port detection successful on %s: %d ports found", host, len(all_ports))
        else:
            _LOGGER.debug("Port detection returned no results on %s", host)
    except Exception as err:
        _LOGGER.debug("Port detection failed on %s: %s (will use manual config)", host, err)
        detected = None
    
    # === CONFIGURE PORTS ===
    if is_first_install:
        # First time setup
        if detected:
            # Auto-configure from detection
            all_ports = sorted(int(p) for p in detected.keys())
            new_options = dict(entry.options)
            new_options[CONF_PORTS] = list(range(1, len(all_ports) + 1))
            
            sfp_ports = [p for p, info in detected.items() if info.get("is_sfp")]
            if sfp_ports:
                new_options["sfp_ports_start"] = min(sfp_ports)
            
            hass.config_entries.async_update_entry(entry, options=new_options)
            _LOGGER.info("First install: auto-configured %d ports on %s (SFP starts at %s)", 
                       len(all_ports), host, new_options.get("sfp_ports_start", "none"))
            
            ports = all_ports.copy()
        else:
            # Detection failed on first install - use defaults and warn user ONCE
            ports = list(range(1, 9))
            new_options = dict(entry.options)
            new_options[CONF_PORTS] = ports
            new_options["detection_failed"] = True  # Flag to show warning in UI
            hass.config_entries.async_update_entry(entry, options=new_options)
            
            _LOGGER.warning(
                "Port detection failed on %s during initial setup. "
                "Using default 8 ports. Please configure manually if incorrect.",
                host
            )
    else:
        # Already configured - use user's settings
        user_ports = entry.options.get(CONF_PORTS, list(range(1, 9)))
        
        if detected:
            # Detection worked - we can use it for interface names/SFP info
            # But respect user's port count preference
            all_detected = sorted(int(p) for p in detected.keys())
            if isinstance(user_ports, list) and user_ports:
                max_user_port = max(user_ports)
                # Use detected ports up to user's limit
                ports = [p for p in all_detected if p <= max_user_port]
                
                # If user configured more ports than detected, fill in the rest
                if max_user_port > max(all_detected):
                    ports.extend(range(max(all_detected) + 1, max_user_port + 1))
            else:
                ports = all_detected.copy()
        else:
            # Detection failed - use user's manual config (no warning after first time)
            ports = user_ports if isinstance(user_ports, list) else list(range(1, 9))
            # Only log at debug level - this is normal for some switches
            _LOGGER.debug("Using manually configured ports on %s (%d ports)", host, len(ports))

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
        "firmware": entry.options.get("oid_firmware", DEFAULT_SYSTEM_OIDS.get("firmware", "")),
        "hostname": entry.options.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
        "uptime": entry.options.get("oid_uptime", DEFAULT_SYSTEM_OIDS.get("uptime", "")),
        "custom": entry.options.get("oid_custom", DEFAULT_SYSTEM_OIDS.get("custom", "")),
    }

    # Create coordinator
    coordinator = SwitchPortCoordinator(
        hass, host, community, ports, base_oids, system_oids, snmp_version, include_vlans, update_seconds
    )
    coordinator.device_name = entry.title
    coordinator.port_mapping = detected or {}  # Empty dict if detection failed
    coordinator.config_entry = entry
    coordinator.update_interval = timedelta(seconds=update_seconds)

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
