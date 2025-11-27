"""Async sensor platform for Switch Port Card Pro."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    UnitOfDataRate,
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
    DEFAULT_BASE_OIDS,
    DEFAULT_PORTS,
    DEFAULT_SYSTEM_OIDS,
    DOMAIN,
)
from .snmp_helper import async_snmp_get, async_snmp_walk

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
        self.mp_model = 0 if snmp_version == "v1" else 1  # v1 → 0, v2c → 1

    async def _async_update_data(self) -> SwitchPortData:
        """Fetch all data asynchronously."""
        try:
            # --- Walk port tables ---
            rx_raw = await async_snmp_walk(
                self.hass,
                self.host,
                self.community,
                self.base_oids["rx"],
                mp_model=self.mp_model,
            )
            tx_raw = await async_snmp_walk(
                self.hass,
                self.host,
                self.community,
                self.base_oids["tx"],
                mp_model=self.mp_model,
            )
            status_raw = await async_snmp_walk(
                self.hass,
                self.host,
                self.community,
                self.base_oids["status"],
                mp_model=self.mp_model,
            )
            speed_raw = await async_snmp_walk(
                self.hass,
                self.host,
                self.community,
                self.base_oids["speed"],
                mp_model=self.mp_model,
            )

            # --- Parse index → value ---
            def parse_table(raw: dict[str, str]) -> dict[int, int]:
                result = {}
                for oid, value in raw.items():
                    try:
                        idx = int(oid.split(".")[-1])
                        result[idx] = int(value)
                    except (ValueError, IndexError):
                        continue
                return result

            rx = parse_table(rx_raw)
            tx = parse_table(tx_raw)
            status = parse_table(status_raw)
            speed = parse_table(speed_raw)

            # --- Build per-port data ---
            ports_data: dict[str, dict[str, Any]] = {}
            total_rx = total_tx = 0

            for port in self.ports:
                raw_status = status.get(port, 2)  # 2 = down
                is_up = raw_status == 1
                port_rx = rx.get(port, 0)
                port_tx = tx.get(port, 0)

                ports_data[str(port)] = {
                    "status": "on" if is_up else "off",
                    "speed": speed.get(port, 0),
                    "rx": port_rx,
                    "tx": port_tx,
                }

                total_rx += port_rx
                total_tx += port_tx

            bandwidth_mbps = round(((total_rx + total_tx) * 8) / (1024 * 1024), 2)

            # --- System OIDs (fallback chain) ---
            system: dict[str, str | None] = {}
            for key in self.system_oids:
                oid = self.system_oids[key]
                if not oid:
                    system[key] = None
                    continue
                try:
                    system[key] = await async_snmp_get(
                        self.hass,
                        self.host,
                        self.community,
                        oid,
                        mp_model=self.mp_model,
                    )
                except Exception:
                    system[key] = None

            # Special Zyxel fallbacks
            if not system.get("cpu") and self.system_oids.get("cpu_zyxel"):
                try:
                    system["cpu"] = await async_snmp_get(
                        self.hass,
                        self.host,
                        self.community,
                        self.system_oids["cpu_zyxel"],
                        mp_model=self.mp_model,
                    )
                except Exception:
                    pass

            if not system.get("memory") and self.system_oids.get("memory_zyxel"):
                try:
                    system["memory"] = await async_snmp_get(
                        self.hass,
                        self.host,
                        self.community,
                        self.system_oids["memory_zyxel"],
                        mp_model=self.mp_model,
                    )
                except Exception:
                    pass

            return SwitchPortData(
                ports=ports_data,
                bandwidth_mbps=bandwidth_mbps,
                system=system,
            )

        except Exception as err:
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name=f"Switch {coordinator.host}",
            manufacturer="SNMP Switch",
            model=coordinator.data.system.get("model", "Generic") if coordinator.data else "Generic",
        )

    @property
    def available(self) -> bool:
        """Return True if data is available."""
        return self.coordinator.data is not None


class BandwidthSensor(SwitchPortBaseEntity):
    """Total bandwidth sensor."""

    _attr_name = "Total Bandwidth"
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id_suffix = "bandwidth"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.bandwidth_mbps if self.coordinator.data else None


class PortStatusSensor(SwitchPortBaseEntity):
    """Port status (on/off) sensor."""

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str, port: int) -> None:
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        self._attr_name = f"Port {port} Status"
        self._attr_unique_id = f"{entry_id}_port_{port}_status"
        self._attr_icon = "mdi:lan-connect" if self.native_value == "on" else "mdi:lan-disconnect"

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.ports.get(self.port, {}).get("status")


class PortSpeedSensor(SwitchPortBaseEntity):
    """Port speed sensor."""

    _attr_native_unit_of_measurement = UnitOfDataRate.BITS_PER_SECOND
    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str, port: int) -> None:
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        self._attr_name = f"Port {port} Speed"
        self._attr_unique_id = f"{entry_id}_port_{port}_speed"

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.ports.get(self.port, {}).get("speed")


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
    snmp_version = entry.options.get("snmp_version", "v2c")

    base_oids = {
        "rx": entry.options.get("oid_rx", DEFAULT_BASE_OIDS["rx"]),
        "tx": entry.options.get("oid_tx", DEFAULT_BASE_OIDS["tx"]),
        "status": entry.options.get("oid_status", DEFAULT_BASE_OIDS["status"]),
        "speed": entry.options.get("oid_speed", DEFAULT_BASE_OIDS["speed"]),
    }

    system_oids = {
        "cpu": entry.options.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu", "")),
        "cpu_zyxel": entry.options.get("oid_cpu_zyxel", DEFAULT_SYSTEM_OIDS.get("cpu_zyxel", "")),
        "memory": entry.options.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory", "")),
        "memory_zyxel": entry.options.get("oid_memory_zyxel", DEFAULT_SYSTEM_OIDS.get("memory_zyxel", "")),
        "hostname": entry.options.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
        "uptime": entry.options.get("oid_uptime", DEFAULT_SYSTEM_OIDS.get("uptime", "")),
    }

    coordinator = SwitchPortCoordinator(
        hass, host, community, ports, base_oids, system_oids, snmp_version
    )

    # Store coordinator for card access
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # First refresh to populate data
    await coordinator.async_config_entry_first_refresh()

    # Create entities
    entities = [BandwidthSensor(coordinator, entry.entry_id)]

    for port in ports:
        entities.append(PortStatusSensor(coordinator, entry.entry_id, port))
        entities.append(PortSpeedSensor(coordinator, entry.entry_id, port))

    async_add_entities(entities)
