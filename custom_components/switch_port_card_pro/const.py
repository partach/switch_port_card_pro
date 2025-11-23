DOMAIN = "switch_port_card_pro"

CONF_HOST = "192.168.1.1"
CONF_COMMUNITY = "public"
CONF_PORTS = "ports"
CONF_INCLUDE_VLANS = "include_vlans"
CONF_BASE_OIDS = "base_oids"

DEFAULT_PORTS = list(range(1, 29))  # XGS1935-28
DEFAULT_BASE_OIDS = {
    "rx": "1.3.6.1.2.1.2.2.1.10",
    "tx": "1.3.6.1.2.1.2.2.1.16",
    "status": "1.3.6.1.2.1.2.2.1.8"
}
