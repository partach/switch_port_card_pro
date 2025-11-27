"""Async sensor platform for Switch Port Card Pro."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    CONF_PORTS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
)
from .snmp_helper import async_snmp_get, async_snmp_walk

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


# ======================================================
# Data Coordinator (FULLY ASYNC)
# ======================================================

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

    async def _async_update_data(self) -> Dict[str, Any]:
        """Perform async SNMP polling."""

        # ---- Walk needed tables ----
        rx = await async_snmp_walk(
            self.hass, self.host, self.community, self.base_oids["rx"]
        )
        tx = await async_snmp_walk(
            self.hass, self.host, self.community, self.base_oids["tx"]
        )
        status = await async_snmp_walk(
            self.hass, self.host, self.community, self.base_oids["status"]
        )
        speed = await async_snmp_walk(
            self.hass, self.host, self.community, self.base_oids["speed"]
        )

        # Convert OID endings to numbers
        def parse(oid_map):
            out = {}
            for oid, value in oid_map.items():
                try:
                    idx = int(oid.split(".")[-1])
                    out[idx] = int(value)
                except Exception:
                    pass
            return out

        rx = parse(rx)
        tx = parse(tx)
        status = parse(status)
        speed = parse(speed)

        # Build port data
        ports_out = {}
        total_rx = 0
        total_tx = 0

        for p in self.ports:
            raw_status = status.get(p, 2)
            is_up = raw_status == 1

            ports_out[str(p)] = {
                "status": "on" if is_up else "off",
                "speed": speed.get(p, 0),
                "rx": rx.get(p, 0),
                "tx": tx.get(p, 0),
            }

            total_rx += rx.get(p, 0)
            total_tx += tx.get(p, 0)

        bandwidth = round(((total_rx + total_tx) * 8) / (1024 * 1024), 2)

        # System OIDs
        system = {}
        for key, oid in self.system_oids.items():
            if not oid:
                system[key] = None
                continue
            try:
                val = await async_snmp_get(
                    self.hass, self.host, self.community, oid
                )
                system[key] = val
            except Exception:
                system[key] = None

        return {
            "ports": ports_out,
            "bandwidth_mbps": bandwidth,
            "system": system,
        }


# ======================================================
# Entities
# ======================================================

class SwitchPortBase(SensorEntity):
    """Base entity."""

    def __init__(self, coordinator, entry_id):
        self.coordinator = coordinator
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name=f"Switch ({coordinator.host})",
            manufacturer="SNMP Switch",
            model="Generic",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None


class BandwidthSensor(SwitchPortBase):
    """Total bandwidth sensor."""

    _attr_name = "Total Bandwidth"
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_bandwidth"

    @property
    def native_value(self):
        return self.coordinator.data.get("bandwidth_mbps")


class PortStatusSensor(SwitchPortBase):
    """Port up/down sensor (string-based for the frontend card)."""

    def __init__(self, coordinator, entry_id, port):
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        self._attr_name = f"Port {port}"
        self._attr_unique_id = f"{entry_id}_port_{port}_status"

    @property
    def native_value(self):
        return self.coordinator.data["ports"][self.port]["status"]


class PortSpeedSensor(SwitchPortBase):
    """Port raw speed sensor."""

    _attr_native_unit_of_measurement = UnitOfDataRate.BITS_PER_SECOND
    _attr_device_class = SensorDeviceClass.DATA_RATE

    def __init__(self, coordinator, entry_id, port):
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        self._attr_name = f"Port {port} Speed"
        self._attr_unique_id = f"{entry_id}_port_{port}_speed"

    @property
    def native_value(self):
        return self.coordinator.data["ports"][self.port]["speed"]


# ======================================================
# Setup entry
# ======================================================

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    host = entry.data[CONF_HOST]
    community = entry.data[CONF_COMMUNITY]

    ports = entry.options.get(CONF_PORTS, DEFAULT_PORTS)

    # Base OIDs now stored inside CONF_BASE_OIDS
    base_oids = entry.options.get("base_oids", DEFAULT_BASE_OIDS)
    system_oids = entry.options.get("system_oids", DEFAULT_SYSTEM_OIDS)

    coordinator = SwitchPortCoordinator(
        hass, host, community, ports, base_oids, system_oids
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()

    entities = [
        BandwidthSensor(coordinator, entry.entry_id),
    ]

    # Create all port sensors
    for port in ports:
        entities.append(PortStatusSensor(coordinator, entry.entry_id, port))
        entities.append(PortSpeedSensor(coordinator, entry.entry_id, port))

    async_add_entities(entities)
