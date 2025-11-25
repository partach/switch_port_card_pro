"""Sensor platform for Switch Port Card Pro."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,          # ← NEW in 2025.2+
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_COMMUNITY,
    CONF_PORTS,
    DEFAULT_PORTS,
    DEFAULT_BASE_OIDS,
    DEFAULT_SYSTEM_OIDS,
)


UPDATE_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    host = entry.data[CONF_HOST]
    community = entry.data[CONF_COMMUNITY]
    ports = entry.options.get(CONF_PORTS, DEFAULT_PORTS)
    base_oids = entry.options.get("base_oids", DEFAULT_BASE_OIDS)
    system_oids = entry.options.get("system_oids", DEFAULT_SYSTEM_OIDS)

    coordinator = SwitchPortCoordinator(hass, host, community, ports, base_oids, system_oids)
    await coordinator.async_config_entry_first_refresh()

    entities = [
        SwitchBandwidthSensor(coordinator, entry),
        SwitchCPUSensor(coordinator, entry),
        SwitchMemorySensor(coordinator, entry),
        SwitchUptimeSensor(coordinator, entry),
        SwitchHostnameSensor(coordinator, entry),
    ]
    for port in ports:
        entities.append(SwitchPortStatusSensor(coordinator, entry, port))

    async_add_entities(entities)


class SwitchPortCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Data coordinator – pysnmp imported lazily inside the class."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        community: str,
        ports: list[int],
        base_oids: dict[str, str],
        system_oids: dict[str, str],
    ) -> None:
        # Lazy import of pysnmp – fixes blocking call in event loop
        from pysnmp.hlapi import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            nextCmd,
        )

        self._hlapi = type("hlapi", (), {
            "CommunityData": CommunityData,
            "ContextData": ContextData,
            "ObjectIdentity": ObjectIdentity,
            "ObjectType": ObjectType,
            "SnmpEngine": SnmpEngine,
            "UdpTransportTarget": UdpTransportTarget,
            "nextCmd": nextCmd,
        })

        self.host = host
        self.community = community
        self.ports = ports
        self.base_oids = base_oids
        self.system_oids = system_oids
        self._previous_octets = 0

        super().__init__(
            hass,
            hass.data.setdefault(DOMAIN, {}).setdefault("logger", hass.log),
            name=f"Switch Port Pro - {host}",
            update_interval=UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            total_octets = 0
            port_status: dict[int, str] = {}
            port_names: dict[int, str] = {}

            for port in self.ports:
                rx = await self._snmp_get(f"{self.base_oids['rx']}.{port}") or 0
                tx = await self._snmp_get(f"{self.base_oids['tx']}.{port}") or 0
                status = await self._snmp_get(f"{self.base_oids['status']}.{port}")
                name = await self._snmp_get(f"{self.base_oids.get('name', '')}.{port}")

                total_octets += rx + tx
                port_status[port] = "up" if status == 1 else "down"
                port_names[port] = str(name).strip() if name else f"Port {port}"

            delta_octets = total_octets - self._previous_octets
            delta_time = UPDATE_INTERVAL.total_seconds()
            mbps = round((delta_octets * 8) / (delta_time * 1_000_000), 1)
            self._previous_octets = total_octets

            cpu = (
                await self._snmp_get(self.system_oids.get("cpu_zyxel"))
                or await self._snmp_get(self.system_oids.get("cpu"))
                or 0
            )
            memory = (
                await self._snmp_get(self.system_oids.get("memory_zyxel"))
                or await self._snmp_get(self.system_oids.get("memory"))
                or 0
            )
            uptime_ticks = await self._snmp_get(self.system_oids["uptime"]) or 0
            hostname = await self._snmp_get(self.system_oids["hostname"]) or "Unknown"

            return {
                "bandwidth_mbps": max(mbps, 0),
                "cpu_percent": cpu,
                "memory_percent": memory,
                "uptime_hours": round(uptime_ticks / 360000, 1),
                "hostname": hostname,
                "port_status": port_status,
                "port_names": port_names,
            }

        except Exception as err:
            raise UpdateFailed(f"SNMP error: {err}") from err

    async def _snmp_get(self, oid: str):
        try:
            iterator = self._hlapi.nextCmd(
                self._hlapi.SnmpEngine(),
                self._hlapi.CommunityData(self.community),
                self._hlapi.UdpTransportTarget((self.host, 161), timeout=2, retries=1),
                self._hlapi.ContextData(),
                self._hlapi.ObjectType(self._hlapi.ObjectIdentity(oid)),
                lexicographicMode=False,
            )
            for errorIndication, errorStatus, _, varBinds in iterator:
                if errorIndication or errorStatus:
                    return None
                if varBinds:
                    value = varBinds[0][1]
                    return int(value) if str(value).isdigit() else str(value)
        except Exception:
            pass
        return None


# ──────────────────────────────────────────────
# Sensor classes
# ──────────────────────────────────────────────
class SwitchPortBaseSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SwitchPortCoordinator, entry: ConfigEntry):
        self.coordinator = coordinator
        self.entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Generic / Zyxel",
            "model": "SNMP Switch",
        }


class SwitchBandwidthSensor(SwitchPortBaseSensor):
    _attr_name = "Total Bandwidth"
    _attr_unique_id = "bandwidth"
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND   # ← Fixed
    _attr_device_class = "data_rate"
    _attr_icon = "mdi:lan-connect"
    @property def native_value(self): return self.coordinator.data["bandwidth_mbps"]


class SwitchCPUSensor(SwitchPortBaseSensor):
    _attr_name = "CPU Usage"
    _attr_unique_id = "cpu"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:chip"
    @property def native_value(self): return self.coordinator.data["cpu_percent"]


class SwitchMemorySensor(SwitchPortBaseSensor):
    _attr_name = "Memory Usage"
    _attr_unique_id = "memory"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:memory"
    @property def native_value(self): return self.coordinator.data["memory_percent"]


class SwitchUptimeSensor(SwitchPortBaseSensor):
    _attr_name = "Uptime"
    _attr_unique_id = "uptime"
    _attr_icon = "mdi:clock-outline"
    @property def native_value(self): return self.coordinator.data["uptime_hours"]
    @property def native_unit_of_measurement(self): return "h"


class SwitchHostnameSensor(SwitchPortBaseSensor):
    _attr_name = "Hostname"
    _attr_unique_id = "hostname"
    _attr_icon = "mdi:identifier"
    @property def native_value(self): return self.coordinator.data["hostname"]


class SwitchPortStatusSensor(SwitchPortBaseSensor):
    _attr_icon = "mdi:ethernet-cable"
    def __init__(self, coordinator: SwitchPortCoordinator, entry: ConfigEntry, port: int):
        super().__init__(coordinator, entry)
        self.port = port
        self._attr_name = f"Port {port}"
        self._attr_unique_id = f"port_{port}"
    @property def native_value(self): return self.coordinator.data["port_status"].get(self.port, "unknown")
    @property def extra_state_attributes(self):
        return {"port": self.port, "description": self.coordinator.data["port_names"].get(self.port, "")}
