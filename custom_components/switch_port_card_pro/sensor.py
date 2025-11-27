"""Async sensor platform for Switch Port Card Pro."""
from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    UnitOfDataRate,
    UnitOfTime,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_COMMUNITY,
    CONF_PORTS,
    CONF_INCLUDE_VLANS,
    DEFAULT_BASE_OIDS,
    DEFAULT_PORTS,
    DEFAULT_SYSTEM_OIDS,
    DOMAIN,
)
from .snmp_helper import async_snmp_get, async_snmp_walk, async_snmp_bulk

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


@dataclass
class SwitchPortData:
    """Data returned by coordinator."""
    ports: dict[str, dict[str, Any]]
    bandwidth_mbps: float
    system: dict[str, str | None]


class SwitchPortCoordinator(DataUpdateCoordinator[SwitchPortData]):
    """Fetch data from the switch."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        community: str,
        ports: List[int],
        base_oids: dict[str, str],
        system_oids: dict[str, str],
        snmp_version: str,
        include_vlans: bool,
    ) -> None:
        """Initialize coordinator."""
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
        self.include_vlans = include_vlans
        self.mp_model = 0 if snmp_version == "v1" else 1

    async def _async_update_data(self) -> SwitchPortData:
        """Fetch all data asynchronously."""
        try:
            # --- WALK PORT TABLES ---
            oids_to_walk = ["rx", "tx", "status", "speed", "name"]
            
            # Conditionally add vlan OID if configured
            if self.include_vlans and self.base_oids.get("vlan"):
                oids_to_walk.append("vlan")

            raw_walk_results = {}
            tasks = []
            for key in oids_to_walk:
                oid = self.base_oids.get(key)
                if oid:
                    tasks.append(async_snmp_walk(
                        self.hass, self.host, self.community, oid, mp_model=self.mp_model,
                    ))

            # Run all port walks concurrently
            walk_results = await asyncio.gather(*tasks)
            
            # Map results back to the OID keys
            walk_map = dict(zip(oids_to_walk, walk_results))

            # --- Parse index → value ---
            def parse_table(raw: dict[str, str], is_int: bool) -> dict[int, Any]:
                """Parse OID table values into index (int) -> value (int/str)."""
                result = {}
                for oid, value in raw.items():
                    try:
                        idx = int(oid.split(".")[-1])
                        if is_int:
                            result[idx] = int(value)
                        else:
                            result[idx] = value
                    except (ValueError, IndexError):
                        continue
                return result

            rx = parse_table(walk_map.get("rx", {}), True)
            tx = parse_table(walk_map.get("tx", {}), True)
            status = parse_table(walk_map.get("status", {}), True)
            speed = parse_table(walk_map.get("speed", {}), True)
            name = parse_table(walk_map.get("name", {}), False)
            vlan = parse_table(walk_map.get("vlan", {}), True)

            # --- Build per-port data ---
            ports_data: dict[str, dict[str, Any]] = {}
            total_rx = total_tx = 0

            for port in self.ports:
                # 1=up, 2=down (per IF-MIB::ifOperStatus)
                raw_status = status.get(port, 2)
                is_up = raw_status == 1
                port_rx = rx.get(port, 0)
                port_tx = tx.get(port, 0)

                ports_data[str(port)] = {
                    "status": "on" if is_up else "off",
                    "speed": speed.get(port, 0),
                    "rx": port_rx,
                    "tx": port_tx,
                    "name": name.get(port, f"Port {port}"),
                    "vlan": vlan.get(port),
                }

                total_rx += port_rx
                total_tx += port_tx

            # Total bandwidth calculation (bytes/s * 8 to get bits/s, then / 1024*1024 for Mbps)
            bandwidth_mbps = round(((total_rx + total_tx) * 8) / (1024 * 1024), 2)

            # --- System OIDs (fallback chain) ---
            system: dict[str, str | None] = {}
            
            # Prepare OIDs for concurrent GET
            system_oids_to_fetch = {
                "cpu": self.system_oids.get("cpu"),
                "memory": self.system_oids.get("memory"),
                "hostname": self.system_oids.get("hostname"),
                "uptime": self.system_oids.get("uptime"),
                "cpu_zyxel": self.system_oids.get("cpu_zyxel"),
                "memory_zyxel": self.system_oids.get("memory_zyxel"),
            }
            
            oids_only = [oid for oid in system_oids_to_fetch.values() if oid]
            
            # Fetch all system OIDs concurrently
            raw_system_results = await async_snmp_bulk(
                self.hass, self.host, self.community, oids_only, mp_model=self.mp_model
            )
            
            def get_oid_value(key_list: List[str]):
                """Get the first non-None result from a list of system keys."""
                for key in key_list:
                    oid = self.system_oids.get(key)
                    if oid:
                        # Find the value in the raw_system_results dictionary
                        value = next((v for k, v in raw_system_results.items() if k.startswith(oid)), None)
                        if value is not None:
                            return value
                return None

            # Apply fallback logic
            system["cpu"] = get_oid_value(["cpu", "cpu_zyxel"])
            system["memory"] = get_oid_value(["memory", "memory_zyxel"])
            system["hostname"] = get_oid_value(["hostname"])
            system["uptime"] = get_oid_value(["uptime"])

            return SwitchPortData(
                ports=ports_data,
                bandwidth_mbps=bandwidth_mbps,
                system=system,
            )

        except Exception as err:
            _LOGGER.error("Error fetching data from %s: %s", self.host, err)
            raise UpdateFailed(f"Error communicating with {self.host}: {err}") from err


# =============================================================================
# Entities
# =============================================================================
class SwitchPortBaseEntity(SensorEntity):
    """Base class for all entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    
    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        """Initialize base entity."""
        self.coordinator = coordinator
        self.entry_id = entry_id
        
        # Initial DeviceInfo setup
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name=f"Switch {coordinator.host}",
            manufacturer="SNMP Switch",
        )
        # Register for update callbacks
        self._attr_extra_state_attributes = {}
        self.remove_listener = coordinator.async_add_listener(self.async_write_ha_state)

    @property
    def available(self) -> bool:
        """Return True if data is available and coordinator is running."""
        return self.coordinator.last_update_success

    async def async_will_remove_from_hass(self):
        """Remove update listener."""
        self.remove_listener()
        await super().async_will_remove_from_hass()

# --- Aggregate and Port Sensors ---

class BandwidthSensor(SwitchPortBaseEntity):
    """Total bandwidth sensor."""

    _attr_name = "Total Bandwidth"
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id_suffix = "total_bandwidth_mbps"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.data.bandwidth_mbps if self.coordinator.data else None


class PortStatusSensor(SwitchPortBaseEntity):
    """Port status (on/off) sensor, acting as the primary port entity."""

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str, port: int) -> None:
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        self._attr_name = f"Port {port} Status"
        self._attr_unique_id = f"{entry_id}_port_{port}_status"
        self._attr_icon = "mdi:lan"

    @property
    def native_value(self) -> str | None:
        """Return the state (on/off)."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.ports.get(self.port, {}).get("status")

    @property
    def icon(self) -> str | None:
        """Return the icon based on state."""
        return "mdi:lan-connect" if self.native_value == "on" else "mdi:lan-disconnect"

    @property
    def extra_state_attributes(self) -> Dict[str, Any] | None:
        """Return the state attributes (speed, traffic, name, vlan)."""
        if not self.coordinator.data:
            return None
        port_data = self.coordinator.data.ports.get(self.port, {})
        
        # Convert raw bytes/s to Mb/s for display
        rx_bps = port_data.get("rx", 0) * 8
        tx_bps = port_data.get("tx", 0) * 8
        
        attrs = {
            "port_name": port_data.get("name"),
            "speed_bps": port_data.get("speed"), # Raw speed in bps
            "rx_bps": rx_bps,
            "tx_bps": tx_bps,
        }
        
        if self.coordinator.include_vlans and port_data.get("vlan") is not None:
            attrs["vlan_id"] = port_data.get("vlan")
            
        return attrs


# --- System Sensors ---

class SystemCpuSensor(SwitchPortBaseEntity):
    """CPU usage sensor."""
    _attr_name = "CPU Usage"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.POWER_FACTOR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id_suffix = "system_cpu"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        try:
            return float(self.coordinator.data.system.get("cpu") or 0)
        except (ValueError, TypeError):
            return None


class SystemMemorySensor(SwitchPortBaseEntity):
    """Memory usage sensor."""
    _attr_name = "Memory Usage"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.POWER_FACTOR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id_suffix = "system_memory"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        try:
            return float(self.coordinator.data.system.get("memory") or 0)
        except (ValueError, TypeError):
            return None


class SystemUptimeSensor(SwitchPortBaseEntity):
    """System Uptime sensor."""
    _attr_name = "Uptime"
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id_suffix = "system_uptime"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor (in seconds)."""
        if not self.coordinator.data:
            return None
        try:
            # Uptime OID typically returns hundredths of a second. Convert to seconds.
            uptime_hsec = int(self.coordinator.data.system.get("uptime") or 0)
            return int(uptime_hsec / 100)
        except (ValueError, TypeError):
            return None


class SystemHostnameSensor(SwitchPortBaseEntity):
    """System Hostname sensor (for device name info)."""
    _attr_name = "Hostname"
    _attr_icon = "mdi:dns"
    _attr_unique_id_suffix = "system_hostname"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.system.get("hostname")


# =============================================================================
# Setup
# =============================================================================
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the platform from config_entry."""
    host = entry.data[CONF_HOST]
    community = entry.data[CONF_COMMUNITY]

    ports = entry.options.get(CONF_PORTS, DEFAULT_PORTS)
    include_vlans = entry.options.get(CONF_INCLUDE_VLANS, False)
    snmp_version = entry.options.get("snmp_version", "v2c")

    # Build OID sets from options, falling back to const.py defaults
    base_oids = {
        "rx": entry.options.get("oid_rx", DEFAULT_BASE_OIDS["rx"]),
        "tx": entry.options.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
        "status": entry.options.get("oid_status", DEFAULT_BASE_OIDS["status"]),
        "speed": entry.options.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
        "name": entry.options.get("oid_name", DEFAULT_BASE_OIDS.get("name", "")),
        "vlan": entry.options.get("oid_vlan", DEFAULT_BASE_OIDS.get("vlan", "")),
    }

    # System OIDs must be mapped to their generic keys for the coordinator logic
    system_oids = {
        "cpu": entry.options.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu", "")),
        "cpu_zyxel": entry.options.get("oid_cpu_zyxel", DEFAULT_SYSTEM_OIDS.get("cpu_zyxel", "")),
        "memory": entry.options.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory", "")),
        "memory_zyxel": entry.options.get("oid_memory_zyxel", DEFAULT_SYSTEM_OIDS.get("memory_zyxel", "")),
        "hostname": entry.options.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
        "uptime": entry.options.get("oid_uptime", DEFAULT_SYSTEM_OIDS.get("uptime", "")),
    }

    coordinator = SwitchPortCoordinator(
        hass, host, community, ports, base_oids, system_oids, snmp_version, include_vlans
    )

    # Store coordinator for card and other platforms to access
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Force first refresh to populate data immediately
  #  await coordinator.async_config_entry_first_refresh()  # see if this fixes the no entities

    # Create entities
    entities = [
        BandwidthSensor(coordinator, entry.entry_id),
        SystemCpuSensor(coordinator, entry.entry_id),
        SystemMemorySensor(coordinator, entry.entry_id),
        SystemUptimeSensor(coordinator, entry.entry_id),
        SystemHostnameSensor(coordinator, entry.entry_id),
    ]

    # Per-port status sensors (traffic/speed data lives in attributes)
    for port in ports:
        entities.append(PortStatusSensor(coordinator, entry.entry_id, port))

    async_add_entities(entities)
