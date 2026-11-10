"""Switch Port Card Pro integration - __init__.py"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_COMMUNITY,
    CONF_HOST,
    CONF_INCLUDE_VLANS,
    CONF_PORTS,
    CONF_SNMP_PORT,
    DEFAULT_BASE_OIDS,
    DEFAULT_SNMP_PORT,
    DEFAULT_SYSTEM_OIDS,
    DOMAIN,
    SNMP_VERSION_TO_MP_MODEL,
)
from .sensor import SwitchPortCoordinator
from .snmp_helper import (
    discover_physical_ports,
)

_LOGGER = logging.getLogger(__name__)

# Required for config-flow-only integrations
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.SENSOR]

# async_install_frontend_resource() copies the card into www/community/ itself,
# so /local/community resolves with or without HACS / the Marketplace.
CARD_FILE = "switch-port-card-pro.js"
CARD_URL = f"/local/community/switch_port_card_pro_card/{CARD_FILE}"

# Home Assistant cancels config entry setups still running when its startup
# stage times out (300 s for all integrations together). Port discovery is
# best-effort, so cap it and fall back to the configured ports instead.
DISCOVERY_TIMEOUT = 60


async def async_install_frontend_resource(hass: HomeAssistant):
    """Ensure the frontend JS file is copied to the www/community folder."""
    
    def install():
        # Source path: custom_components/switch_port_card_pro/frontend/switch-port-card-pro.js
        source_path = hass.config.path("custom_components", DOMAIN, "frontend", "switch-port-card-pro.js")
        
        # Target path: www/community/switch_port_card_pro/
        target_dir = hass.config.path("www", "community", "switch_port_card_pro_card") # legacy naming
        target_path = os.path.join(target_dir, "switch-port-card-pro.js")

        try:
            # 1. Ensure the destination directory exists
            if not os.path.exists(target_dir):
                _LOGGER.debug("Creating directory: %s", target_dir)
                os.makedirs(target_dir, exist_ok=True)

            # 2. Check if source exists and copy
            if os.path.exists(source_path):
                # Using copy2 to preserve metadata (timestamps)
                shutil.copy2(source_path, target_path)
                # A leftover pre-compressed copy (e.g. from a HACS install) would be
                # served instead of the fresh .js and pin the card to an old version.
                stale_gz = target_path + ".gz"
                if os.path.exists(stale_gz):
                    os.remove(stale_gz)
                _LOGGER.info("Updated frontend resource: %s", target_path)
            else:
                _LOGGER.warning("Frontend source file missing at %s", source_path)
                
        except Exception as err:  # noqa: BLE001 - frontend copy is optional; never block setup
            _LOGGER.error("Failed to install frontend resource: %s", err)

    # Offload the blocking file operations to the executor thread
    await hass.async_add_executor_job(install)

def _is_card_resource(url: str) -> bool:
    """Return True if a Lovelace resource URL points at our card.

    Only the file name is compared. HACS served the card from /hacsfiles/...,
    while the HA 2026.11 Marketplace serves it from /local/community/... and
    rewrites existing entries in place, keeping their ID. Comparing the full URL
    misses the rewritten entry, so a duplicate was added on every restart.
    """
    return url.split("?")[0].endswith(f"/{CARD_FILE}")


async def async_register_card(hass: HomeAssistant, entry: ConfigEntry):
    """Register the custom card as a Lovelace resource, exactly once."""
    lovelace_data = hass.data.get("lovelace")
    if not lovelace_data:
        _LOGGER.debug("Unable to get lovelace data (new api 2026.2)")
        return  # Lovelace not loaded

    resources = lovelace_data.resources
    if not resources:
        _LOGGER.debug("Unable to get resources (new api 2026.2)")
        return  # not loaded

    if not getattr(resources, "loaded", True):
        await resources.async_load()

    existing = [
        item for item in resources.async_items()
        if _is_card_resource(item.get("url", ""))
    ]

    # In YAML mode the resource collection is read-only.
    if not hasattr(resources, "async_create_item"):
        if not existing:
            _LOGGER.warning(
                "Lovelace is in YAML mode - add %s to your resources manually", CARD_URL
            )
        return

    if existing:
        # Clear up duplicates left behind by earlier versions, keeping the first.
        for duplicate in existing[1:]:
            item_id = duplicate.get("id")
            if not item_id:
                continue
            try:
                await resources.async_delete_item(item_id)
            except (HomeAssistantError, KeyError, ValueError) as err:
                _LOGGER.debug(
                    "Could not remove duplicate card resource %s: %s",
                    duplicate.get("url"), err
                )
            else:
                _LOGGER.info("Removed duplicate card resource: %s", duplicate.get("url"))

        _LOGGER.debug("Card already registered: %s", existing[0].get("url"))
        return

    try:
        await resources.async_create_item({
            "res_type": "module",
            "url": CARD_URL,
        })
    except (HomeAssistantError, KeyError, ValueError) as err:
        _LOGGER.warning("Could not register card resource %s: %s", CARD_URL, err)
        return
    _LOGGER.debug("Card registered: %s", CARD_URL)

def _migrate_host_ids(hass: HomeAssistant, entry: ConfigEntry, host: str) -> None:
    """Keep the device and port sensors when the switch's address changes.

    Their IDs embed the host. Rewrite IDs that still carry an earlier host, so
    history and dashboards stay attached instead of new entities being created
    next to orphaned ones.
    """
    prefix = f"{entry.entry_id}_"
    port_re = re.compile(rf"^{re.escape(prefix)}(.+)_port_(\d+)_status$")

    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        m = port_re.match(reg_entry.unique_id)
        if not m or m.group(1) == host:
            continue
        new_id = f"{prefix}{host}_port_{m.group(2)}_status"
        if ent_reg.async_get_entity_id(reg_entry.domain, DOMAIN, new_id):
            continue  # an entity for the new host exists already; leave both
        ent_reg.async_update_entity(reg_entry.entity_id, new_unique_id=new_id)
        _LOGGER.info("Moved %s to host %s", reg_entry.entity_id, host)

    dev_reg = dr.async_get(hass)
    new_ident = (DOMAIN, f"{prefix}{host}")
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        old = {
            ident for ident in device.identifiers
            if ident[0] == DOMAIN and ident[1].startswith(prefix) and ident != new_ident
        }
        if not old or new_ident in device.identifiers:
            continue
        try:
            dev_reg.async_update_device(
                device.id, new_identifiers=(device.identifiers - old) | {new_ident}
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not move device %s to host %s: %s", device.id, host, err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Switch Port Card Pro from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
        _LOGGER.info("Setting up %s", DOMAIN)
    await async_install_frontend_resource(hass) # copy to card to the location it is supposed to be at.
    await async_register_card(hass,entry)
    host = entry.data[CONF_HOST]
    community = entry.data[CONF_COMMUNITY]
    update_seconds = max(3, entry.options.get("update_interval", 20))
    include_vlans = entry.options.get(CONF_INCLUDE_VLANS, True)
    snmp_version = entry.options.get("snmp_version", "v2c")
    # The config flow stores the SNMP port in data; options never held it.
    snmp_port = entry.options.get(CONF_SNMP_PORT, entry.data.get(CONF_SNMP_PORT, DEFAULT_SNMP_PORT))
    mp_model = SNMP_VERSION_TO_MP_MODEL.get(snmp_version, 1)

    # === PORT DISCOVERY WITH SMART FALLBACK ===
    detected = None
    ports = None
    manufacturer = "Unknown"  # Initialize here, outside try block
    detection_summary = "manual"  # Initialize here too
    is_first_install = CONF_PORTS not in entry.options
    
    try:
        async with asyncio.timeout(DISCOVERY_TIMEOUT):
            detected = await discover_physical_ports(hass, host, community, snmp_port, mp_model)
        if detected:
            # --- EXTRACT METADATA ---
            # Get a sample port to pull device-wide info (all ports share the same device info)
            sample_info = next(iter(detected.values()))
            manufacturer = sample_info.get("manufacturer", "Unknown")
            detection_summary = _get_detection_summary(detected)
            
            all_ports = sorted(int(p) for p in detected)
            
            # Log detailed discovery results
            copper_count = sum(1 for p in detected.values() if p.get("is_copper"))
            sfp_count = len(detected) - copper_count
            speed_summary = _summarize_port_speeds(detected)
            
            _LOGGER.info(
                "Port detection successful on %s (%s): %d ports found → "
                "%d copper, %d SFP/SFP+ | Speeds: %s | Detection: %s",
                host, manufacturer, len(all_ports), copper_count, sfp_count, 
                speed_summary, detection_summary
            )
        else:
            _LOGGER.debug("Port detection returned no results on %s", host)
    except TimeoutError:
        _LOGGER.warning(
            "Port detection on %s did not finish within %d seconds; "
            "using the configured ports instead",
            host, DISCOVERY_TIMEOUT,
        )
        detected = None
    except Exception as err:  # noqa: BLE001 - detection is best-effort; falls back to manual config
        _LOGGER.debug("Port detection failed on %s: %s (will use manual config)", host, err)
        detected = None
    
    # === CONFIGURE PORTS ===
    if is_first_install:
        new_options = dict(entry.options)
        
        if detected:
            # Auto-configure from detection
            all_ports = sorted(int(p) for p in detected)
            new_options[CONF_PORTS] = all_ports
            
            # Store SFP port range
            sfp_ports = [p for p, info in detected.items() if info.get("is_sfp")]
            if sfp_ports:
                new_options["sfp_ports_start"] = min(sfp_ports)
                new_options["sfp_ports_end"] = max(sfp_ports)
            
            new_options["manufacturer"] = manufacturer
            new_options["auto_detected"] = True
            new_options["detection_method"] = detection_summary
            
            _LOGGER.info(
                "First install: auto-configured %d ports on %s (%s) | SFP: %s | Detection: %s", 
                len(all_ports), host, manufacturer,
                f"ports {min(sfp_ports)}-{max(sfp_ports)}" if sfp_ports else "none",
                detection_summary
            )
            ports = all_ports.copy()
        else:
            # Fallback for failed detection on first install
            ports = list(range(1, 9))
            new_options[CONF_PORTS] = ports
            new_options["detection_failed"] = True
            new_options["manufacturer"] = "Unknown"
            new_options["auto_detected"] = False
            new_options["detection_method"] = "failed"
            
            _LOGGER.warning(
                "Port detection failed on %s during initial setup. "
                "Using default 8 ports. Please configure manually if incorrect.",
                host
            )
        
        hass.config_entries.async_update_entry(entry, options=new_options)
    
    else:
        # Already configured - Update metadata if we have fresh detection results
        user_ports = entry.options.get(CONF_PORTS, list(range(1, 9)))
        
        if detected:
            new_options = dict(entry.options)
            
            # Extract manufacturer from detection
            sample_info = next(iter(detected.values()))
            manufacturer = sample_info.get("manufacturer", "Unknown")
            detection_summary = _get_detection_summary(detected)
            
            # 1. Update Manufacturer if it was unknown or changed
            old_manufacturer = entry.options.get("manufacturer", "Unknown")
            if manufacturer != "Unknown" and old_manufacturer != manufacturer:
                new_options["manufacturer"] = manufacturer
                _LOGGER.info("Updated manufacturer for %s: %s → %s", 
                           host, old_manufacturer, manufacturer)
            
            # 2. Update detection metadata
            new_options["detection_method"] = detection_summary
            
            # 3. Port validation and configuration
            all_detected = sorted(int(p) for p in detected)
            
            if isinstance(user_ports, list) and user_ports:
                max_user_port = max(user_ports)
                
                # Warn if user configured more ports than detected
                if max_user_port > len(all_detected):
                    _LOGGER.warning(
                        "User configured %d ports on %s, but only %d detected. "
                        "Extra ports may not work correctly.",
                        max_user_port, host, len(all_detected)
                    )
                
                # Use detected ports up to user's limit
                ports = [p for p in all_detected if p <= max_user_port]
                
                # If user configured more ports than detected, fill in the rest
                if max_user_port > max(all_detected):
                    ports.extend(range(max(all_detected) + 1, max_user_port + 1))
            else:
                # User didn't configure specific ports, use all detected
                ports = all_detected.copy()
            
            # Update SFP port range if detected
            sfp_ports = [p for p, info in detected.items() if info.get("is_sfp")]
            if sfp_ports:
                new_options["sfp_ports_start"] = min(sfp_ports)
                new_options["sfp_ports_end"] = max(sfp_ports)
            
            # Only update entry if something changed
            if new_options != entry.options:
                hass.config_entries.async_update_entry(entry, options=new_options)
                _LOGGER.debug("Updated config entry metadata for %s", host)
        else:
            # Detection failed - use user's manual config
            ports = user_ports if isinstance(user_ports, list) else list(range(1, 9))
            manufacturer = entry.options.get("manufacturer", "Unknown")
            
            _LOGGER.debug(
                "Using manually configured ports on %s (%d ports) - detection unavailable",
                host, len(ports)
            )

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

    _migrate_host_ids(hass, entry, host)

    # Create coordinator
    coordinator = SwitchPortCoordinator(
        hass, host, community, snmp_port, ports, base_oids, system_oids,
        snmp_version, include_vlans, update_seconds
    )
    coordinator.device_name = entry.title
    coordinator.port_mapping = detected or {}  # Empty dict if detection failed
    coordinator.manufacturer = manufacturer
    coordinator.config_entry = entry
    coordinator.update_interval = timedelta(seconds=update_seconds)

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Populate coordinator data before entities are created and subscribed.
    await coordinator.async_config_entry_first_refresh()

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    return True


def _summarize_port_speeds(detected: dict) -> str:
    """
    Summarize port speeds for logging.
    
    Example output: "8×1000Mbps, 2×10000Mbps"
    """
    speed_counts = {}
    for port_info in detected.values():
        speed = port_info.get("speed_mbps", 0)
        if speed > 0:
            speed_counts[speed] = speed_counts.get(speed, 0) + 1
    
    if not speed_counts:
        return "unknown speeds"
    
    # Sort by speed for consistent output
    parts = [f"{count}×{speed}Mbps" for speed, count in sorted(speed_counts.items())]
    return ", ".join(parts)


def _get_detection_summary(detected: dict) -> str:
    """
    Get summary of detection methods used.
    
    Example output: "8 by name, 2 by type"
    """
    method_counts = {}
    for port_info in detected.values():
        method = port_info.get("detection", "unknown")
        method_counts[method] = method_counts.get(method, 0) + 1
    
    parts = [f"{count} by {method}" for method, count in sorted(method_counts.items())]
    return ", ".join(parts) if parts else "manual"


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called when options are changed – force full reload."""
    await hass.config_entries.async_reload(entry.entry_id)
