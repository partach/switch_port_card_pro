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
    DOMAIN,
    SNMP_VERSION_TO_MP_MODEL,
)
from .snmp_helper import (
    async_snmp_walk,
    async_snmp_bulk,
)
_LOGGER = logging.getLogger(__name__)



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
        snmp_port,
        ports: list[int],
        base_oids: dict[str, str],
        system_oids: dict[str, str],
        snmp_version: str,
        include_vlans: bool,
        update_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=update_seconds),
        )
        self.host = host
        self.community = community
        self.snmp_port = snmp_port
        self.ports = ports
        self.base_oids = base_oids
        self.system_oids = system_oids
        self.include_vlans = include_vlans
        self.mp_model = SNMP_VERSION_TO_MP_MODEL.get(snmp_version, 1)
        self.port_mapping = {}
        self.update_seconds = update_seconds
        self._last_total_bytes = 0

    async def _async_update_data(self) -> SwitchPortData:
        try:

            if not self.port_mapping:
                # Fallback if detection somehow failed in __init__
                self.port_mapping = {
                    p: {"if_index": p, "name": f"Port {p}", "is_sfp": False, "is_copper": True}
                    for p in self.ports
                }   
            # === PORT WALKS ===
            oids_to_walk = ["rx", "tx", "status", "speed", "name", "poe_power", "poe_status","port_custom"]
            if self.include_vlans and self.base_oids.get("vlan"):
                oids_to_walk.append("vlan")

            tasks = [
                async_snmp_walk(self.hass, self.host, self.community, self.snmp_port, self.base_oids[k], mp_model=self.mp_model)
                for k in oids_to_walk if self.base_oids.get(k)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            walk_map: dict[str, dict[str, str]] = {}
            for key, result in zip([k for k in oids_to_walk if self.base_oids.get(k)], results):
                if isinstance(result, Exception):
                    _LOGGER.error("SNMP walk failed for %s: %s", key, result)
                    walk_map[key] = {}
                elif not result:
               #     _LOGGER.warning("SNMP walk empty for %s → using defaults", key) # surpress unneeded log
                    walk_map[key] = {}
                else:
                    walk_map[key] = result

            def parse(raw: dict[str, str], int_val: bool = True) -> dict[int, Any]:
                out = {}
                for oid, val in raw.items():
                    try:
                        idx = int(oid.split(".")[-1])
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
            port_custom = parse(walk_map.get("port_custom", {}))

            ports_data: dict[str, dict[str, Any]] = {}
            total_rx = total_tx = total_poe_mw = 0

            for port in self.ports:
                p = str(port)
                port_info = self.port_mapping.get(port) or {}
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
                    "port_custom": 0,
                }

                # Use the real if_index for all lookups
                if any(if_index in t for t in (status, speed, rx, tx, poe_power)):
                    HighLowSpeed = speed.get(if_index, 0)
                    if HighLowSpeed < 100000: # check if we use the 32 or 64 bit variant
                        HighLowSpeed = HighLowSpeed * 1000000 # convert to bps
                    ports_data[p].update({
                        "status": "on" if status.get(if_index, 2) == 1 else "off",
                        "speed": HighLowSpeed,
                        "rx": rx.get(if_index, 0),
                        "tx": tx.get(if_index, 0),
                        "name": name.get(if_index, f"Port {port}"),
                        "vlan": vlan.get(if_index),
                        "poe_power": poe_power.get(if_index, 0),
                        "poe_status": poe_status.get(if_index, 0),
                        "port_custom": port_custom.get(if_index, 0),
                    })

                total_rx += rx.get(if_index, 0)
                total_tx += tx.get(if_index, 0)
                total_poe_mw += poe_power.get(if_index, 0)

            # compute current totals (these are lifetime counters) in bytes
            current_total_bytes = total_rx + total_tx
            # compute delta from last poll
            delta_total = current_total_bytes - getattr(self, "_last_total_bytes", 0)
            # handle negative (counter reset or wrap) if needed
            if delta_total < 0:
                # Heuristic: assume 32-bit wrap if last_total was large
                MAX32 = 4294967296
                if getattr(self, "_last_total_bytes", 0) > 3_000_000_000:
                    delta_total = (MAX32 - self._last_total_bytes) + current_total_bytes
                else:
                    # real reset, treat as zero
                    delta_total = 0
            # prefer using configured stable interval if available
            delta_time = getattr(self, "update_seconds", 20)
            if delta_time <= 0:
                delta_time = 20
            # Mbps: megabits per second
            bandwidth_mbps = round((delta_total * 8) / (1024 * 1024) / delta_time, 2)

            # store for next run
            self._last_total_bytes = current_total_bytes
            # === SYSTEM OIDs ===
            raw_system = await async_snmp_bulk(
                self.hass,
                self.host,
                self.community,
                self.SNMPport,
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
                "poe_total_watts": round(total_poe_mw / 1000.0, 2) if total_poe_mw > 0 else None,
                "custom": get("custom"),
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

        # STATIC DEVICE INFO (never changes)
        sys_info = coordinator.data.system if coordinator.data else {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self.coordinator.host}")},
            connections=set(),
            name=f"Switch {self.coordinator.host}",  # temporary before SNMP poll
            manufacturer=sys_info.get("manufacturer") or "Generic SNMP",
            model=sys_info.get("model") or f"{entry_id}",          # updated dynamically later
            sw_version=sys_info.get("firmware"),          # updated dynamically later
        )

        # Auto update entity state when coordinator updates
        self._unsub_coordinator = coordinator.async_add_listener(self.async_write_ha_state)

    @property
    def available(self) -> bool:
        """Return True only if we have data."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
        )

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
            model = (system.get("model") or "")
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
        if not self.coordinator.data:
            return 0
        try:
            val = self.coordinator.data.system.get("poe_total_watts")
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return 0
        
class BandwidthSensor(SwitchPortBaseEntity):
    """Total bandwidth sensor."""

    _attr_name = "Total Bandwidth"
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_icon = "mdi:speedometer"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id_suffix = "total_bandwidth_mbps"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return 0
        try:
            val = self.coordinator.data.bandwidth_mbps
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return 0

class FirmwareSensor(SwitchPortBaseEntity):
    _attr_name = "Firmware"
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_firmware"

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return ""
        try:
            return self.coordinator.data.system.get("firmware")
        except (ValueError, TypeError):
            return ""
        
class PortStatusSensor(SwitchPortBaseEntity):
    """Port status (on/off) sensor, acting as the primary port entity."""
    _attr_has_entity_name = True
    _attr_should_poll = False
    
    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str, port: int) -> None:
        super().__init__(coordinator, entry_id)
        self.port = str(port)
        self._attr_name = f"Port {port} Status"
        self._attr_unique_id = f"{entry_id}_{self.coordinator.host}_port_{port}_status"
        self._attr_icon = "mdi:lan"

        # For live traffic calculation
        self._last_rx_bytes: int | None = None
        self._last_tx_bytes: int | None = None
        self._last_update: float | None = None

    @property
    def native_value(self) -> str | None:
        """Return the state (on/off)."""
        if not self.coordinator.data:
            return ""
        try:
            return self.coordinator.data.ports.get(self.port, {}).get("status")
        except (ValueError, TypeError):
            return ""

    @property
    def icon(self) -> str | None:
        """Return the icon based on state."""
        return "mdi:lan-connect" if self.native_value == "on" else "mdi:lan-disconnect"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        try:    
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
    
                actual_delta = now - self._last_update
                delta_time = actual_delta if actual_delta < (self.coordinator.update_seconds * 1.5) else self.coordinator.update_seconds
    
                if delta_time > 0:
                    # --- RAW DELTAS ---
                    delta_rx = raw_rx_bytes - self._last_rx_bytes
                    delta_tx = raw_tx_bytes - self._last_tx_bytes
            
                    # --- HANDLE 32-bit WRAPAROUND ---
                    # Most switches use 32-bit counters for ifHC* until > 4GB
                    MAX32 = 4294967296  # 2^32
            
                    if delta_rx < 0:
                        # If previous value was "close" to wrap limit → wrap happened
                        if self._last_rx_bytes > 3_000_000_000:
                            delta_rx = (MAX32 - self._last_rx_bytes) + raw_rx_bytes
            
                    if delta_tx < 0:
                        if self._last_tx_bytes > 3_000_000_000:
                            delta_tx = (MAX32 - self._last_tx_bytes) + raw_tx_bytes
    
            
                    # --- COMPUTE LIVE BPS ---
                    rx_bps_live = int(delta_rx * 8 / delta_time)
                    tx_bps_live = int(delta_tx * 8 / delta_time)
            
                    # --- FINAL SAFETY CLAMP ---
                    MAX_SAFE_BPS = 20_000_000_000
                    if rx_bps_live < 0 or rx_bps_live > MAX_SAFE_BPS:
                        _LOGGER.warning("RX counter reset or spurious data detected. Dropping rate data.")
                        rx_bps_live = 0
                        
                    if tx_bps_live < 0 or tx_bps_live > MAX_SAFE_BPS:
                        _LOGGER.warning("TX counter reset or spurious data detected. Dropping rate data.")
                        tx_bps_live = 0
    
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
                "custom": p.get("port_custom"),
            }
            if self.coordinator.include_vlans and p.get("vlan") is not None:
                attrs["vlan_id"] = p["vlan"]
            if has_poe:
                attrs.update({
                    "poe_power_watts": round(p.get("poe_power", 0) / 1000.0, 2),
                    "poe_enabled": p.get("poe_status") in (1, 2, 4),
                    "poe_class": p.get("poe_status"),
                })
            return attrs
        except Exception as e:
          _LOGGER.debug("Error calculating live traffic for port %s: %s", self.port, e)
        return {}

# --- System Sensors ---

class SystemCpuSensor(SwitchPortBaseEntity):
    """CPU usage sensor."""
    _attr_name = "CPU Usage"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_icon = "mdi:cpu-64-bit"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id_suffix = "system_cpu"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return 0
        try:
            return float(self.coordinator.data.system.get("cpu") or 0)
        except (ValueError, TypeError):
            return 0
            
class CustomValueSensor(SwitchPortBaseEntity):
    _attr_name = "Custom Value"
    _attr_icon = "mdi:text-box-search"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_custom_value"

    @property
    def native_value(self):
        """Return the custom OID value safely."""
        if not self.coordinator.data:
            return ""
        try:
            return self.coordinator.data.system.get("custom")
        except (ValueError, TypeError):
            return ""

class SystemMemorySensor(SwitchPortBaseEntity):
    """Memory usage sensor."""
    _attr_name = "Memory Usage"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_icon = "mdi:memory"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_unique_id_suffix = "system_memory"

    def __init__(self, coordinator: SwitchPortCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_{self._attr_unique_id_suffix}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return 0
        try:
            return float(self.coordinator.data.system.get("memory") or 0)
        except (ValueError, TypeError):
            return 0


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
            return 0
        try:
            # Uptime OID typically returns hundredths of a second. Convert to seconds.
            uptime_hsec = int(self.coordinator.data.system.get("uptime") or 0)
            return int(uptime_hsec / 100)
        except (ValueError, TypeError):
            return 0


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
            return ""
        try:
            return self.coordinator.data.system.get("hostname")
        except (ValueError, TypeError):
            return ""


# =============================================================================
# Setup
# =============================================================================
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the platform from config_entry. vlans override always to true"""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Create entities
    entities = [
        BandwidthSensor(coordinator, entry.entry_id),
        TotalPoESensor(coordinator, entry.entry_id),
        SystemCpuSensor(coordinator, entry.entry_id),
        CustomValueSensor(coordinator, entry.entry_id),
        FirmwareSensor(coordinator, entry.entry_id),
        SystemMemorySensor(coordinator, entry.entry_id),
        SystemUptimeSensor(coordinator, entry.entry_id),
        SystemHostnameSensor(coordinator, entry.entry_id),
    ]

    # Per-port status sensors (traffic/speed data lives in attributes)
    for port in coordinator.ports:
        entities.append(PortStatusSensor(coordinator, entry.entry_id, port))

    async_add_entities(entities)
