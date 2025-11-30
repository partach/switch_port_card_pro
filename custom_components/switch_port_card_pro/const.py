"""Constants for Switch Port Card Pro."""

from typing import Final

DOMAIN: Final = "switch_port_card_pro"

# Config entry keys
CONF_HOST: Final = "host"
CONF_COMMUNITY: Final = "community"
CONF_PORTS: Final = "ports"
CONF_INCLUDE_VLANS: Final = "include_vlans"

# Option keys (used in config flow)
CONF_OID_RX: Final = "oid_rx"
CONF_OID_TX: Final = "oid_tx"
CONF_OID_STATUS: Final = "oid_status"
CONF_OID_SPEED: Final = "oid_speed"
CONF_OID_NAME: Final = "oid_name"
CONF_OID_VLAN: Final = "oid_vlan"
CONF_OID_POE_POWER: Final = "oid_poe_power"
CONF_OID_POE_STATUS: Final = "oid_poe_status"
CONF_OID_POE_TOTAL: Final = "oid_poe_total"
CONF_OID_CPU: Final = "oid_cpu"
CONF_OID_MEMORY: Final = "oid_memory"
CONF_OID_FIRMWARE: Final = "oid_firmware"
CONF_OID_HOSTNAME: Final = "oid_hostname"
CONF_OID_UPTIME: Final = "oid_uptime"

# Default monitored ports (1–28 is safe for most 24+4 switches)
DEFAULT_PORTS: Final = list(range(1, 9)) # remove 29 as this is too many for most users

# Default per-port OIDs (standard + common working ones)
DEFAULT_BASE_OIDS: Final = {
    "rx": "1.3.6.1.2.1.2.2.1.10",        # ifInOctets (32-bit)
    "tx": "1.3.6.1.2.1.2.2.1.16",        # ifOutOctets (32-bit)
    "status": "1.3.6.1.2.1.2.2.1.8",     # ifOperStatus
    "speed": "1.3.6.1.2.1.2.2.1.5",      # ifSpeed
    "name": "1.3.6.1.2.1.31.1.1.1.18",   # ifAlias (modern description)
    "vlan": "",                          # User must set per-brand (e.g. Q-BRIDGE-MIB or private)
    "poe_power": "",                     # User must set (common: Cisco/Zyxel/TP-Link)
    "poe_status": "",                    # User must set
}

# Default system-level OIDs (most common working ones)
DEFAULT_SYSTEM_OIDS: Final = {
    "cpu": "",                           # Usually private — user sets
    "memory": "",                        # Usually private
    "firmware": "",                      # Usually private
    "hostname": "1.3.6.1.2.1.1.5.0",     # sysName — works everywhere
    "uptime": "1.3.6.1.2.1.1.3.0",       # sysUpTime — universal
    "poe_total": "",                     # Usually private — user sets
}
