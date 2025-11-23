from homeassistant.components.sensor import SensorEntity, PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_HOST, CONF_NAME, DATA_RATE_MEGABITS_PER_SECOND, PERCENTAGE
)
from homeassistant.helpers.entity import DeviceEntity
from homeassistant.util import Throttle
from datetime import timedelta
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from pysnmp.hlapi import *

from .const import DOMAIN, CONF_COMMUNITY, CONF_PORTS, DEFAULT_BASE_OIDS

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)

PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_COMMUNITY): cv.string,
    vol.Optional(CONF_NAME, default="Switch Port Card Pro"): cv.string,
    vol.Optional(CONF_PORTS, default=DEFAULT_PORTS): cv.ensure_list,
})

def setup_platform(hass, config, add_entities, discovery_info=None):
    host = config[CONF_HOST]
    community = config[CONF_COMMUNITY]
    name = config[CONF_NAME]
    ports = config[CONF_PORTS]

    monitor = SwitchPortMonitor(host, community, ports)
    entities = [
        SwitchBandwidthSensor(monitor, name),
        SwitchCPUSensor(monitor, name),
        SwitchMemorySensor(monitor, name),
        SwitchUptimeSensor(monitor, name),
    ]
    for port in ports:
        entities.append(SwitchPortStatusSensor(monitor, name, port))

    add_entities(entities, True)

class SwitchPortMonitor:
    def __init__(self, host, community, ports):
        self._host = host
        self._community = community
        self._ports = ports
        self.data = {}

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        total_bytes = 0
        port_status = {}
        cpu = 0
        memory = 0
        uptime = 0

        for port in self._ports:
            rx_oid = f"{DEFAULT_BASE_OIDS['rx']}.{port}"
            tx_oid = f"{DEFAULT_BASE_OIDS['tx']}.{port}"
            status_oid = f"{DEFAULT_BASE_OIDS['status']}.{port}"

            rx = self._snmp_get(rx_oid) or 0
            tx = self._snmp_get(tx_oid) or 0
            status = self._snmp_get(status_oid)

            total_bytes += rx + tx
            port_status[port] = "up" if status == 1 else "down"

        cpu = self._snmp_get(DEFAULT_BASE_OIDS['cpu']) or 0
        memory = self._snmp_get(DEFAULT_BASE_OIDS['memory']) or 0
        uptime = self._snmp_get("1.3.6.1.2.1.1.3.0") or 0

        delta = total_bytes - getattr(self, '_prev_bytes', 0)
        mbps = (delta * 8) / (MIN_TIME_BETWEEN_UPDATES.total_seconds() * 1_000_000)

        self.data = {
            "bandwidth_mbps": round(mbps, 1),
            "cpu_percent": cpu,
            "memory_percent": memory,
            "uptime": uptime / 3600,  # timeticks to hours
            "port_status": port_status,
        }
        self._prev_bytes = total_bytes

    def _snmp_get(self, oid):
        for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
            SnmpEngine(),
            CommunityData(self._community),
            UdpTransportTarget((self._host, 161)),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
        ):
            if errorIndication or errorStatus:
                return None
            return int(varBinds[0][1])

class SwitchBandwidthSensor(SensorEntity):
    def __init__(self, monitor, name):
        self._monitor = monitor
        self._attr_name = f"{name} Bandwidth"
        self._attr_unique_id = f"{name.lower().replace(' ', '_')}_bandwidth"
        self._attr_unit_of_measurement = DATA_RATE_MEGABITS_PER_SECOND
        self._attr_device_class = "data_rate"
        self._attr_icon = "mdi:lan"

    def update(self):
        self._monitor.update()
        self._attr_native_value = self._monitor.data["bandwidth_mbps"]

class SwitchCPUSensor(SensorEntity):
    def __init__(self, monitor, name):
        self._monitor = monitor
        self._attr_name = f"{name} CPU"
        self._attr_unique_id = f"{name.lower().replace(' ', '_')}_cpu"
        self._attr_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:chip"

    def update(self):
        self._monitor.update()
        self._attr_native_value = self._monitor.data["cpu_percent"]

class SwitchMemorySensor(SensorEntity):
    def __init__(self, monitor, name):
        self._monitor = monitor
        self._attr_name = f"{name} Memory"
        self._attr_unique_id = f"{name.lower().replace(' ', '_')}_memory"
        self._attr_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:memory"

    def update(self):
        self._monitor.update()
        self._attr_native_value = self._monitor.data["memory_percent"]

class SwitchUptimeSensor(SensorEntity):
    def __init__(self, monitor, name):
        self._monitor = monitor
        self._attr_name = f"{name} Uptime"
        self._attr_unique_id = f"{name.lower().replace(' ', '_')}_uptime"
        self._attr_icon = "mdi:clock-outline"

    def update(self):
        self._monitor.update()
        self._attr_native_value = self._monitor.data["uptime"]

class SwitchPortStatusSensor(SensorEntity):
    def __init__(self, monitor, name, port):
        self._monitor = monitor
        self._port = port
        self._attr_name = f"{name} Port {port}"
        self._attr_unique_id = f"{name.lower().replace(' ', '_')}_port_{port}"
        self._attr_icon = "mdi:ethernet"

    def update(self):
        self._monitor.update()
        self._attr_native_value = self._monitor.data["port_status"].get(self._port, "unknown")
