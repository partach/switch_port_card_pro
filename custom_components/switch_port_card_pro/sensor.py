"""Async sensor platform for Switch Port Card Pro."""
from __future__ import annotations
import logging
import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from homeassistant.helpers import device_registry
from datetime import datetime
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
from homeassistant.core import HomeAssistant, callback
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
    SNMP_VERSION_TO_MP_MODEL,
)
from .snmp_helper import (
    async_snmp_walk,
    async_snmp_bulk,
    discover_physical_ports,
)
_LOGGER = logging.getLogger(__name__)
UPDATE_INTERVAL = timedelta(seconds=20)


@dataclass
class SwitchPortData:
    ports: dict[str, dict[str, Any]]
    bandwidth_mbps: float
    system: dict[str, Any]


class SwitchPortCoordinator(DataUpdateCoordinator[SwitchPortData]):
    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        community: str,
        ports: list[int],
        base_oids: dict[str, str],
        system_oids: dict[str, str],
        snmp_version: str,
        include_vlans: bool,
    ) -> None:
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
        self.mp_model = SNMP_VERSION_TO_MP_MODEL.get(snmp_version, 1)
        self.port_mapping = {}

    async def _async_update_data(self) -> SwitchPortData:
        try:
            if not self.port_mapping:
                detected = await discover_physical_ports(
                    self.hass, self.host, self.community, mp_model=self.mp_model
                )
                self.port_mapping = detected or {
                    p: {"if_index": p, "name": f"Port {p}", "is_sfp": False, "is_copper": True}
                    for p in self.ports
                }            
            # === PORT WALKS ===
            oids_to_walk = ["rx", "tx", "status", "speed", "name", "poe_power", "poe_status"]
            if self.include_vlans and self.base_oids.get("vlan"):
                oids_to_walk.append("vlan")

            tasks = [
                async_snmp_walk(self.hass, self.host, self.community, self.base_oids[k], mp_model=self.mp_model)
                for k in oids_to_walk if self.base_oids.get(k)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            walk_map: dict[str, dict[str, str]] = {}
            for key, result in zip([k for k in oids_to_walk if self.base_oids.get(k)], results):
                if isinstance(result, Exception):
                    _LOGGER.error("SNMP walk failed for %s: %s", key, result)
                    walk_map[key] = {}
                elif not result:
                    _LOGGER.warning("SNMP walk empty for %s → using defaults", key)
                    walk_map[key] = {}
                else:
                    walk_map[key] = result

            def parse(raw: dict[str, str], int_val: bool = True) -> dict[int, Any]:
                out = {}
                for oid, val in raw.items():
                    try:
                        parts = oid.split(".")
                        idx = int(parts[-2]) if len(parts) > 1 and parts[-1] == '0' else int(parts[-1])
                        out[idx] = int(val) if int_val else val
                    except (ValueError, IndexError):
                        continue
                return out

            rx = parse(walk_map.get("rx", {}))
            tx = parse(walk_map.get("tx", {}))
            status = parse(walk_map.get("status", {}))
            speed = parse(walk_map.get("speed", {}))
            name = parse(walk_map.get("name", {}), int_val=False)
            vlan = parse(walk_map.get("vlan", {}))
            poe_power = parse(walk_map.get("poe_power", {}))
            poe_status = parse(walk_map.get("poe_status", {}))

            ports_data: dict[str, dict[str, Any]] = {}
            total_rx = total_tx = total_poe_mw = 0

            for port in self.ports:
                p = str(port)
                port_info = self.port_mapping.get(port) or {}
                if not port_info:
                    continue  # Skip if no mapping
                if_index = port_info.get("if_index", port)  # fallback to port number if no mapping
                ports_data[p] = {
                    "status": "off",
                    "speed": 0,
                    "rx": 0,
                    "tx": 0,
                    "name": f"Port {port}",
                    "vlan": None,
                    "poe_power": 0,
                    "poe_status": 0,
                }

                # Use the real if_index for all lookups

                ports_data[p].update({
                    "status": "on" if status.get(if_index, 2) == 1 else "off",
                    "speed": speed.get(if_index, 0),
                    "rx": rx.get(if_index, 0),
                    "tx": tx.get(if_index, 0),
                    "name": name.get(if_index, f"Port {port}"),
                    "vlan": vlan.get(if_index),
                    "poe_power": poe_power.get(if_index, 0),
                    "poe_status": poe_status.get(if_index, 0),
                })

                total_rx += rx.get(if_index, 0)
                total_tx += tx.get(if_index, 0)
                total_poe_mw += poe_power.get(if_index, 0)

            bandwidth_mbps = round(((total_rx + total_tx) * 8) / (1024 * 1024 * UPDATE_INTERVAL.total_seconds()), 2)

            # === SYSTEM OIDs ===
            raw_system = await async_snmp_bulk(
                self.hass,
                self.host,
                self.community,
                [oid for oid in self.system_oids.values() if oid],
                mp_model=self.mp_model,
            )

            def get(oid_key: str) -> str | None:
                oid = self.system_oids.get(oid_key)
                return next((v for k, v in raw_system.items() if oid and k.startswith(oid)), None)

            system = {
                "cpu": get("cpu") or get("cpu_zyxel"),
                "memory": get("memory") or get("memory_zyxel"),
                "hostname": get("hostname"),
                "uptime": get("uptime"),
                "firmware": get("firmware"),
                "model": get("model"),
                "poe_total_watts": round(total_poe_mw / 1000.0, 2) if total_poe_mw > 0 else None,
                "poe_total_raw": get("poe_total"),
            }

            return SwitchPortData(ports=ports_data, bandwidth_mbps=bandwidth_mbps, system=system)

        except Exception as err:
            _LOGGER.exception("Update failed for %s", self.host)
            raise UpdateFailed(str(err)) from err

# =============================================================================
# Entities
# =============================================================================
class SwitchPortBaseEntity(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        self.coordinator = coordinator
        self.entry_id = entry_id

        # Only identifiers + connections go here — everything else is updated dynamically later
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self.coordinator.host}")},
            name=f"Switch Port: {self.coordinator.host}",
            manufacturer="Generic SNMP Switch",
            model="Unknown/Discovering",
        )
        # Auto update entity state when coordinator updates
        self._unsub_coordinator = coordinator.async_add_listener(self.async_write_ha_state)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_will_remove_from_hass(self) -> None:
        if hasattr(self, '_unsub_coordinator') and self._unsub_coordinator:
            self._unsub_coordinator()
        if hasattr(self, '_unsub_devinfo') and self._unsub_devinfo:
            self._unsub_devinfo()
        await super().async_will_remove_from_hass()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _update_device_info() -> None:
            """
            Update HA device registry with dynamic system info.
            """
            if not self.coordinator.data:
                return

            system = self.coordinator.data.system

            raw_hostname = system.get("hostname") or ""
            device_name = raw_hostname.strip() or f"Switch {self.coordinator.host}"
            model = (system.get("model") or "Unknown")
            firmware = system.get("firmware")

            # Update device registry entry
            dev_reg = device_registry.async_get(self.hass)
            device_entry = dev_reg.async_get_device(
                    identifiers={(DOMAIN, f"{self.entry_id}_{self.coordinator.host}")}
            )
            if device_entry:
                dev_reg.async_update_device(
                device_entry.id,
                name=device_name,
                model=model,
                sw_version=firmware,
                )

        # Run on each coordinator update
        self._unsub_devinfo = self.coordinator.async_add_listener(_update_device_info)

        # Also run immediately on entity creation (if we already have data)
        if self.coordinator.data:
            _update_device_info()




# --- Aggregate and Port Sensors ---
class TotalPoESensor(SwitchPortBaseEntity):
    _attr_name = "Total PoE Power"
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_total_poe"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.system.get("poe_total_watts") if self.coordinator.data else None
        
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

class FirmwareSensor(SwitchPortBaseEntity):
    _attr_name = "Firmware"
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_firmware"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.system.get("firmware") if self.coordinator.data else None
        
class PortStatusSensor(SwitchPortBaseEntity):
    """Port status (on/off) sensor, acting as the primary port entity."""
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "on"]    
    _attr_has_entity_name = True
    _attr_should_poll = False
    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str, port: int) -> None:
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        self._attr_name = f"Port {port}"
        self._attr_unique_id = f"{entry_id}_port_{port}_status"
        self._attr_icon = "mdi:lan"

        # For live traffic calculation
        self._last_rx_bytes: int | None = None
        self._last_tx_bytes: int | None = None
        self._last_update: float | None = None

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
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        p = self.coordinator.data.ports.get(self.port, {})
        
        # === LIFETIME VALUES (always available) ===
        raw_rx_bytes = p.get("rx", 0)
        raw_tx_bytes = p.get("tx", 0)

        # === LIVE RATE CALCULATION (only if we have previous data) ===
        now = datetime.now().timestamp()
        rx_bps_live = 0
        tx_bps_live = 0

        if (self._last_rx_bytes is not None
            and self._last_tx_bytes is not None
            and self._last_update is not None
            and now > self._last_update):

            delta_time = now - self._last_update
            if delta_time > 0:
                rx_bps_live = int((raw_rx_bytes - self._last_rx_bytes) * 8 / delta_time)
                tx_bps_live = int((raw_tx_bytes - self._last_tx_bytes) * 8 / delta_time)

        # Store for next poll
        self._last_rx_bytes = raw_rx_bytes
        self._last_tx_bytes = raw_tx_bytes
        self._last_update = now
        port_info = self.coordinator.port_mapping.get(int(self.port), {})
        has_poe = (
            p.get("poe_power", 0) > 0 or
            p.get("poe_status", 0) > 0 or
            self.coordinator.base_oids.get("poe_power") or
            self.coordinator.base_oids.get("poe_status")
        )
        attrs = {
            "port_name": p.get("name"),
            "speed_bps": p.get("speed"),
            # Legacy — kept for old cards / backward compatibility
            "rx_bps": raw_rx_bytes * 8,
            "tx_bps": raw_tx_bytes * 8,
            # NEW — real live rates (used when card has show_live_traffic: true)
            "rx_bps_live": rx_bps_live,
            "tx_bps_live": tx_bps_live,
            # SFP / Copper detection (universal — works on Zyxel, TP-Link, QNAP, ASUS, etc.)
            "is_sfp": bool(port_info.get("is_sfp", False)),
            "is_copper": bool(port_info.get("is_copper", True)),
            "interface": port_info.get("if_descr"),  # e.g. "eth5"
        }
        if self.coordinator.include_vlans and p.get("vlan") is not None:
            attrs["vlan_id"] = p["vlan"]
        if has_poe:
            attrs.update({
                "poe_power": round(p.get("poe_power", 0) / 1000.0, 2),
                "poe_enabled": p.get("poe_enabled") in (1, 2, 4),
                "poe_status": p.get("poe_status"),
            })
        return attrs

# --- System Sensors ---

class SystemCpuSensor(SwitchPortBaseEntity):
    """CPU usage sensor."""
    _attr_name = "CPU Usage"
    _attr_native_unit_of_measurement = PERCENTAGE
 #   _attr_device_class = SensorDeviceClass.POWER_FACTOR
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
    include_vlans = entry.options.get(CONF_INCLUDE_VLANS, False)
    snmp_version = entry.options.get("snmp_version", "v2c")
    mp_model = SNMP_VERSION_TO_MP_MODEL.get(snmp_version, 1)  # defaults to v2c
    
    # AUTO-DETECT PORTS
    detected = await discover_physical_ports(hass, host, community, mp_model)

    # Check if user explicitly set a port limit in Options
    user_limit = entry.options.get(CONF_PORTS)  # can be None, [], or [1,2,...,n]

    if detected:
        ports = list(detected.keys())  # ← all auto-detected ports: 28, 26, 52, whatever
    else:
        # Nothing detected → fall back to classic 8 ports
        ports = list(range(1, 9))  # or keep DEFAULT_PORTS if you prefer
        _LOGGER.warning("Auto-detection failed on %s → using default 8 ports", host)
    # Build OID sets from options, falling back to const.py defaults
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

    # System OIDs must be mapped to their generic keys for the coordinator logic
    system_oids = {
        "cpu": entry.options.get("oid_cpu", DEFAULT_SYSTEM_OIDS.get("cpu", "")),
        "memory": entry.options.get("oid_memory", DEFAULT_SYSTEM_OIDS.get("memory", "")),
        "firmware": entry.options.get("oid_firmware", DEFAULT_SYSTEM_OIDS.get("firmware", "")),
        "hostname": entry.options.get("oid_hostname", DEFAULT_SYSTEM_OIDS.get("hostname", "")),
        "uptime": entry.options.get("oid_uptime", DEFAULT_SYSTEM_OIDS.get("uptime", "")),
        "poe_total": entry.options.get("oid_poe_total", DEFAULT_SYSTEM_OIDS.get("poe_total", "")),
    }

    coordinator = SwitchPortCoordinator(
        hass, host, community, ports, base_oids, system_oids, snmp_version, include_vlans
    )

    coordinator.device_name = entry.title
    coordinator.port_mapping = detected or {}
    # Store coordinator for card and other platforms to access
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Force first refresh to populate data immediately
    # this makes it not work, dunno why:
    # await coordinator.async_config_entry_first_refresh()  # see if this fixes the no entities

    # Create entities
    entities = [
        BandwidthSensor(coordinator, entry.entry_id),
        TotalPoESensor(coordinator, entry.entry_id),
        SystemCpuSensor(coordinator, entry.entry_id),
        FirmwareSensor(coordinator, entry.entry_id),
        SystemMemorySensor(coordinator, entry.entry_id),
        SystemUptimeSensor(coordinator, entry.entry_id),
        SystemHostnameSensor(coordinator, entry.entry_id),
    ]

    # Per-port status sensors (traffic/speed data lives in attributes)
    for port in ports:
        entities.append(PortStatusSensor(coordinator, entry.entry_id, port))

    async_add_entities(entities)
