"""Sensor platform for Switch Port Card Pro."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import asyncio

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfDataRate, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

# ha_blocking_import: pysnmp
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

_SNMP_EXECUTOR = ThreadPoolExecutor(max_workers=5)
UPDATE_INTERVAL = timedelta(seconds=30)

# ======================================================================
# SNMP Helpers
# ======================================================================

def _snmp_get(host: str, community: str, oid: str) -> Optional[Any]:
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
    result = {}
    try:
        for (errInd, errStat, errIdx, varBinds) in nextCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((host, 161), timeout=3, retries=1),
            ObjectType(ObjectIdentity(base_oid)),
            lookupMib=False,
        ):
            if errInd or errStat:
                break
            for vb in varBinds:
                # Store keys as string OID
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
        host = self.host
        community = self.community
        
        # 1. Walk Tables
        # We need RX/TX for bandwidth calc, Status/Speed for visuals
        rx_walk = _snmp_walk(host, community, self.base_oids.get("rx", ""))
        tx_walk = _snmp_walk(host, community, self.base_oids.get("tx", ""))
        status_walk = _snmp_walk(host, community, self.base_oids.get("status", ""))
        speed_walk = _snmp_walk(host, community, self.base_oids.get("speed", ""))

        # Helper to parse walk results by last OID index
        def parse_walk(walk_data):
            res = {}
            for oid, val in walk_data.items():
                try:
                    idx = int(oid.split(".")[-1])
                    res[idx] = int(val)
                except Exception:
                    pass
            return res

        rx_map = parse_walk(rx_walk)
        tx_map = parse_walk(tx_walk)
        status_map = parse_walk(status_walk)
        speed_map = parse_walk(speed_walk)

        ports_out = {}
        total_rx = 0
        total_tx = 0

        for p in self.ports:
            # SNMP Status: 1=up, 2=down
            raw_status = status_map.get(p, 2)
            is_up = (raw_status == 1)
            
            # SNMP Speed is usually in bps (some switches use other units, standard is bps)
            raw_speed = speed_map.get(p, 0)
            
            rx = rx_map.get(p, 0)
            tx = tx_map.get(p, 0)
            
            ports_out[str(p)] = {
                "rx": rx,
                "tx": tx,
                "status": "on" if is_up else "off", # Converted for JS card
                "speed": raw_speed
            }

            total_rx += rx
            total_tx += tx

        # Bandwidth Calc (Total MBps across all ports)
        # Note: Counter overflow logic is not handled here, basic polling
        bandwidth = round(((total_rx + total_tx) * 8) / (1024 * 1024), 2)

        # 2. System OIDs
        sys_data = {
            "cpu": None, "memory": None, "uptime": None, "hostname": None
        }
        
        # Simple helpers for single OIDs
        def get_single(key, fallback=None):
            oid = self.system_oids.get(key) or fallback
            if not oid: return None
            val = _snmp_get(host, community, oid)
            return val

        try:
            cpu_val = get_single("cpu", self.system_oids.get("cpu_zyxel"))
            if cpu_val is not None: sys_data["cpu"] = int(cpu_val)
        except: pass

        try:
            mem_val = get_single("memory", self.system_oids.get("memory_zyxel"))
            if mem_val is not None: sys_data["memory"] = int(mem_val)
        except: pass

        try:
            up_val = get_single("uptime")
            if up_val is not None: sys_data["uptime"] = int(up_val) / 100
        except: pass

        try:
            name_val = get_single("hostname")
            if name_val is not None: sys_data["hostname"] = str(name_val)
        except: pass

        return {
            "ports": ports_out,
            "bandwidth_mbps": bandwidth,
            "system": sys_data,
        }

# ======================================================================
# Entities
# ======================================================================

class SwitchPortBaseSensor(SensorEntity):
    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str):
        self.coordinator = coordinator
        self.entry_id = entry_id
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name=f"Switch {coordinator.host}",
            manufacturer="SNMP Switch",
            model="Generic",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None

class SwitchBandwidthSensor(SwitchPortBaseSensor):
    _attr_name = "Total Bandwidth"
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_bandwidth"

    @property
    def native_value(self):
        return self.coordinator.data.get("bandwidth_mbps")

class SystemSensor(SwitchPortBaseSensor):
    def __init__(self, coordinator, entry_id, key, name, unit=None):
        super().__init__(coordinator, entry_id)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{key}"
        if unit: self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        return self.coordinator.data.get("system", {}).get(self.key)

# --- PORT SENSORS ---

class SwitchPortStatusSensor(SwitchPortBaseSensor):
    """Status sensor: returns 'on' or 'off'."""
    # We use a string sensor here because the JS card looks for "on"/"up" strings
    # A BinarySensor is technically more correct in HA, but string is safer for custom cards 
    # that parse raw state.

    def __init__(self, coordinator, entry_id, port):
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        # Naming is critical for the JS _find() function
        self._attr_name = f"Port {port}"
        self._attr_unique_id = f"{entry_id}_port_{port}"

    @property
    def native_value(self):
        return self.coordinator.data.get("ports", {}).get(self.port, {}).get("status")

class SwitchPortSpeedSensor(SwitchPortBaseSensor):
    """Speed sensor: returns raw bps integer."""
    _attr_native_unit_of_measurement = UnitOfDataRate.BITS_PER_SECOND
    _attr_device_class = SensorDeviceClass.DATA_RATE

    def __init__(self, coordinator, entry_id, port):
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        self._attr_name = f"Port Speed {port}"
        self._attr_unique_id = f"{entry_id}_port_speed_{port}"

    @property
    def native_value(self):
        return self.coordinator.data.get("ports", {}).get(self.port, {}).get("speed")

# ======================================================================
# Setup
# ======================================================================

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    host = entry.data[CONF_HOST]
    community = entry.data[CONF_COMMUNITY]
    ports = entry.options.get(CONF_PORTS, DEFAULT_PORTS)

    base_oids = {
        "rx": entry.options.get("oid_rx", DEFAULT_BASE_OIDS["rx"]),
        "tx": entry.options.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
        "status": entry.options.get("oid_status", DEFAULT_BASE_OIDS["status"]),
        "speed": entry.options.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
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
    
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_config_entry_first_refresh()

    entities = [
        SwitchBandwidthSensor(coordinator, entry.entry_id),
        SystemSensor(coordinator, entry.entry_id, "cpu", "CPU", "%"),
        SystemSensor(coordinator, entry.entry_id, "memory", "Memory", "%"),
        SystemSensor(coordinator, entry.entry_id, "uptime", "Uptime", "s"),
    ]

    for port in ports:
        # We only create Status and Speed sensors because the visual card
        # relies on them. RX/TX per port is often overkill for HA recorder db
        # unless you specifically need graphs for every port.
        entities.append(SwitchPortStatusSensor(coordinator, entry.entry_id, port))
        entities.append(SwitchPortSpeedSensor(coordinator, entry.entry_id, port))

    async_add_entities(entities)
