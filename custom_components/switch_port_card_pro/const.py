DOMAIN = "switch_port_card_pro"

CONF_HOST = "host"
CONF_COMMUNITY = "community"
CONF_PORTS = "ports"
CONF_INCLUDE_VLANS = "include_vlans"
CONF_BASE_OIDS = "base_oids"
CONF_POE_POWER_OID = "poe_power_oid"      # e.g. per-port PoE consumption
CONF_POE_STATUS_OID = "poe_status_oid"    # e.g. PoE enabled/disabled per port
CONF_POE_TOTAL_OID = "poe_total_oid"      # optional: total PoE budget used
# Default number of ports (Tested Zyxel has 28)
DEFAULT_PORTS = list(range(1, 29))

DEFAULT_BASE_OIDS = {
    "rx": "1.3.6.1.2.1.2.2.1.10",
    "tx": "1.3.6.1.2.1.2.2.1.16",
    "status": "1.3.6.1.2.1.2.2.1.8",
    "speed": "1.3.6.1.2.1.2.2.1.5",
    "name": "1.3.6.1.2.1.31.1.1.1.18",
    "vlan": "1.3.6.1.4.1.9.9.68.1.2.2.1.2", 
    "poe_power": "1.3.6.1.4.1.9.9.91.1.1.1.1.4",   # per-port power draw in mW
    "poe_status": "1.3.6.1.2.1.105.1.1.1.3",  # 1=enabled, 2=disabled, etc.
}
# System-level OIDs (most common ones)
# Users can override these in config_flow options

DEFAULT_SYSTEM_OIDS = {
    "cpu": "1.3.6.1.4.1.2021.11.11.0",           # UCD-SNMP-MIB (Linux, many switches)
    "firmware": "1.3.6.1.4.1.890.1.5.1.1.1.0",   # firmware string
    "memory": "1.3.6.1.4.1.2021.4.6.0",           # UCD-SNMP-MIB total used
    "uptime": "1.3.6.1.2.1.1.3.0",                 # sysUpTime (standard)
    "hostname": "1.3.6.1.2.1.1.5.0",               # sysName
    "poe_total": "1.3.6.1.4.1.9.9.91.1.2.1.1.5",   # total PoE consumption
}
