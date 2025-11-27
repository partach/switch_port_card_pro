# --- File: custom_components/switch_port_card_pro/snmp_helper.py ---

from homeassistant.core import HomeAssistant
from pysnmp.hlapi.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    getCmd,
)

async def async_snmp_get(hass: HomeAssistant, host: str, community: str, oid: str) -> str:
    """Asynchronously perform an SNMP GET request for a single OID."""

    def snmp_get_sync() -> str:
        """Synchronously perform the SNMP GET request."""
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(
                SnmpEngine(),
                CommunityData(community),
                UdpTransportTarget((host, 161), timeout=5, retries=1),
                ContextData(),
                ObjectIdentity(oid),
            )
        )

        if errorIndication:
            raise ConnectionError(f"SNMP Connection Error: {errorIndication}")
        if errorStatus:
            raise ValueError(f"SNMP Error Status: {errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or '?'}")

        # Return the value (usually a tuple like (OID, Value))
        return str(varBinds[0][1])

    # Run the synchronous SNMP call in a separate thread (executor)
    # to prevent blocking the Home Assistant event loop.
    return await hass.async_add_executor_job(snmp_get_sync)

# --- End of snmp_helper.py ---
