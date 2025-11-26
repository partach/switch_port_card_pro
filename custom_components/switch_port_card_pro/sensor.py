"""Sensor platform for Switch Port Card Pro."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import asyncio

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfDataRate, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from pysnmp.hlapi import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ObjectType,
    ObjectIdentity,
    getCmd,
    nextCmd,
)

from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    CONF_PORTS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
)

_LOGGER = logging.getLogger(__name__)

# SNMP executor pool
_SNMP_EXECUTOR = ThreadPoolExecutor(max_workers=3)

# Recommended safe polling interval
UPDATE_INTERVAL = timedelta(seconds=30)


# ======================================================================
# SNMP helper functions (run in executor)
# ======================================================================

def _snmp_get(host: str, community: str, oid: str) -> Optional[Any]:
    """Perform SNMP GET (blocking)."""
    try:
        iterator = getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((host, 161), timeout=2, retries=1),
            ObjectType(ObjectIdentity(oid)),
        )
        errInd, errStat, errIdx, varBinds = next(iterator)
        if errInd or errStat:
            return None
        return varBinds[0][1]
    except Exception:
        return None


def _snmp_walk(host: str, community: str, base_oid: str) -> Dict[str, Any]:
    """Perform SNMP WALK (blocking)."""
    result = {}
    try:
        for (errInd, errStat, errIdx, varBinds) in nextCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((host, 161), timeout=2, retries=1),
            ObjectType(ObjectIdentity(base_oid)),
            lookupMib=False,
        ):
            if errInd or errStat:
                break
            for vb in varBinds:
                result[str(vb[0])] = vb[1]
    except Exception:
        pass
    return result


# ======================================================================
# Coordinator
# ======================================================================

class SwitchPortCoordinator(DataUpdateCoordinator):
    """Coordinates all SNMP polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        community: str,
        ports: List[int],
        base_oids: Dict[str, str],
        system_oids: Dict[str, str],
    ):
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=UPDATE_INTERVAL,
        )
        self.hass = hass
        self.host = host
        self.community = community
        self.ports = ports
        self.base_oids = base_oids
        self.system_oids = system_oids
        self.data = {}

    async def _async_update_data(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_SNMP_EXECUTOR, self._poll)

    def _poll(self) -> Dict[str, Any]:
        """Blocking SNMP collection."""
        host = self.host
        community = self.community
        ports_out = {}

        # Walk RX/TX tables
        rx_walk = _snmp_walk(host, community, self.base_oids.get("rx", ""))
        tx_walk = _snmp_walk(host, community, self.base_oids.get("tx", ""))

        rx_map = {}
        tx_map = {}
        for oid, val in rx_walk.items():
            try:
                idx = int(oid.split(".")[-1])
                rx_map[idx] = int(val)
            except Exception:
                pass
        for oid, val in tx_walk.items():
            try:
                idx = int(oid.split(".")[-1])
                tx_map[idx] = int(val)
            except Exception:
                pass

        # Per-port data
        for p in self.ports:
            ports_out[str(p)] = {
                "rx": rx_map.get(p, 0),
                "tx": tx_map.get(p, 0),
            }

        # Total bandwidth
        total_rx = sum(v["rx"] for v in ports_out.values())
        total_tx = sum(v["tx"] for v in ports_out.values())
        bandwidth = round(((total_rx + total_tx) * 8) / (1024 * 1024), 2)

        # System OIDs
        cpu = None
        mem = None
        uptime_s = None
        hostname = None

        cpu_oid = self.system_oids.get("cpu") or self.system_oids.get("cpu_zyxel")
        mem_oid = self.system_oids.get("memory") or self.system_oids.get("memory_zyxel")

        if cpu_oid:
            try: cpu = int(_snmp_get(host, community, cpu_oid) or 0)
            except: cpu = None

        if mem_oid:
            try: mem = int(_snmp_get(host, community, mem_oid) or 0)
            except: mem = None

        if self.system_oids.get("uptime"):
            try:
                uptime_ticks = int(_snmp_get(host, community, self.system_oids["uptime"]) or 0)
                uptime_s = uptime_ticks / 100
            except:
                uptime_s = None

        if self.system_oids.get("hostname"):
            try:
                hostname = _snmp_get(host, community, self.system_oids["hostname"])
                hostname = str(hostname) if hostname else None
            except:
                hostname = None

        return {
            "ports": ports_out,
            "bandwidth_mbps": bandwidth,
            "system": {
                "cpu": cpu,
                "memory": mem,
                "uptime": uptime_s,
                "hostname": hostname,
            },
        }


# ======================================================================
# Base Sensor Entity
# ======================================================================

class SwitchPortBaseSensor(SensorEntity):
    """Base class for all sensors in the integration."""

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str):
        self.coordinator = coordinator
        self.entry_id = entry_id

        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name=f"Switch {coordinator.host}",
            manufacturer="Generic Switch",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None


# ======================================================================
# Individual Sensors
# ======================================================================

class SwitchBandwidthSensor(SwitchPortBaseSensor):
    """Total combined RX+TX bandwidth."""

    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str):
        super().__init__(coordinator, entry_id)
        self._attr_name = "Switch Total Bandwidth"
        self._attr_unique_id = f"{entry_id}_bandwidth"

    @property
    def native_value(self):
        return self.coordinator.data.get("bandwidth_mbps")


class SystemCpuSensor(SwitchPortBaseSensor):
    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_name = "Switch CPU"
        self._attr_unique_id = f"{entry_id}_cpu"

    @property
    def native_value(self):
        return self.coordinator.data.get("system", {}).get("cpu")


class SystemMemorySensor(SwitchPortBaseSensor):
    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_name = "Switch Memory"
        self._attr_unique_id = f"{entry_id}_memory"

    @property
    def native_value(self):
        return self.coordinator.data.get("system", {}).get("memory")


class SystemUptimeSensor(SwitchPortBaseSensor):
    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_name = "Switch Uptime (seconds)"
        self._attr_unique_id = f"{entry_id}_uptime"

    @property
    def native_value(self):
        return self.coordinator.data.get("system", {}).get("uptime")


class PortTrafficSensor(SwitchPortBaseSensor):
    """Per-port RX or TX sensor."""

    def __init__(self, coordinator, entry_id: str, port: int, direction: str):
        super().__init__(coordinator, entry_id)
        self.port = port
        self.direction = direction
        self._attr_name = f"Port {port} {direction.upper()}"
        self._attr_unique_id = f"{entry_id}_port_{port}_{direction}"

    @property
    def native_value(self):
        return (
            self.coordinator.data.get("ports", {})
            .get(str(self.port), {})
            .get(self.direction, 0)
        )


# ======================================================================
# Setup entry (called automatically by HA)
# ======================================================================

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors when a config entry is loaded."""
    host = entry.data[CONF_HOST]
    community = entry.data[CONF_COMMUNITY]
    ports = entry.options.get(CONF_PORTS, DEFAULT_PORTS)

    # Build OID sets
    base_oids = {
        "rx": entry.options.get("oid_rx", DEFAULT_BASE_OIDS["rx"]),
        "tx": entry.options.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
        "status": entry.options.get("oid_status", DEFAULT_BASE_OIDS["status"]),
        "speed": entry.options.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
        "name": entry.options.get("oid_name", DEFAULT_BASE_OIDS["name"]),
    }

    system_oids = {
        "cpu": entry.options.get("oid_cpu", DEFAULT_SYSTEM_OIDS["cpu"]),
        "memory": entry.options.get("oid_memory", DEFAULT_SYSTEM_OIDS["memory"]),
        "hostname": entry.options.get("oid_hostname", DEFAULT_SYSTEM_OIDS["hostname"]),
        "uptime": entry.options.get("oid_uptime", DEFAULT_SYSTEM_OIDS["uptime"]),
    }

    coordinator = SwitchPortCoordinator(
        hass, host, community, ports, base_oids, system_oids
    )
    # ###### CRITICAL LINES ######
    # Store coordinator so the card can find the device via device_id

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Force first refresh so entities have data immediately
    await coordinator.async_config_entry_first_refresh()
    # #########################

    entities = [
        SwitchBandwidthSensor(coordinator, entry.entry_id),
        SystemCpuSensor(coordinator, entry.entry_id),
        SystemMemorySensor(coordinator, entry.entry_id),
        SystemUptimeSensor(coordinator, entry.entry_id),
    ]

    # Per-port sensors
    for port in ports:
        entities.append(PortTrafficSensor(coordinator, entry.entry_id, port, "rx"))
        entities.append(PortTrafficSensor(coordinator, entry.entry_id, port, "tx"))

    async_add_entities(entities)
