"""Async SNMP helper – works perfectly with pysnmp-lextudio 7.x+ (v3arch)"""
from __future__ import annotations
import logging
import asyncio
from typing import Literal, Dict

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    walk_cmd,
)

_LOGGER = logging.getLogger(__name__)
_SNMP_ENGINE = SnmpEngine()

# KILL MIB LOADING — THIS IS THE HOLY GRAIL
# _SNMP_ENGINE.get_mib_builder().set_mib_sources()  # ← NO MORE BLOCKING I/O EVER
# does not work at all!!

# 0 = SNMPv1, 1 = SNMPv2c
MpModel = Literal[0, 1]


async def async_snmp_get(
    hass,
    host: str,
    community: str,
    oid: str,
    timeout: int = 10,
    retries: int = 3,
    mp_model: MpModel = 1,
) -> str | None:
    """Ultra-reliable async SNMP GET."""
    transport = None
    try:
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries

        error_indication, error_status, error_index, var_binds = await get_cmd(
            _SNMP_ENGINE,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )

        if error_indication:
            if "timeout" in str(error_indication).lower():
                _LOGGER.debug("SNMP GET timeout: %s (oid=%s)", host, oid)
            else:
                _LOGGER.debug("SNMP GET error indication: %s", error_indication)
            return None

        if error_status:
            msg = error_status.prettyPrint()
            if "noSuchName" in msg or "noSuchObject" in msg:
                return None
            _LOGGER.debug("SNMP GET error status: %s", msg)
            return None

        return var_binds[0][1].prettyPrint() if var_binds else None

    except Exception as exc:
        _LOGGER.debug("SNMP GET exception on %s (oid=%s): %s", host, oid, exc)
        return None

    finally:
        if transport:
            try:
                await transport.close()
            except (asyncio.CancelledError, ConnectionError, OSError):
                # These are expected during shutdown or network issues
                pass
            except Exception as exc:  # Only log unexpected ones
                _LOGGER.debug("Unexpected error closing SNMP transport: %s", exc)


async def async_snmp_walk(
    hass,
    host: str,
    community: str,
    base_oid: str,
    timeout: int = 10,
    retries: int = 3,
    mp_model: MpModel = 1,
) -> dict[str, str]:
    """
    Async SNMP WALK using the high-level walkCmd.
    Returns {full_oid: value} for all OIDs under base_oid.
    """
    results: dict[str, str] = {}
    transport = None

    try:
        # Create and configure transport
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries

        # Use walk_cmd for the operation
        # Note: walk_cmd returns a list of (errorIndication, errorStatus, errorIndex, varBinds) tuples
        # But in v3arch.asyncio it returns an async iterator yielding these tuples
        iterator = walk_cmd(
            _SNMP_ENGINE,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
            ignoreNonIncreasingOid=True,
        )

        async for error_indication, error_status, error_index, var_binds in iterator:
            if error_indication:
                _LOGGER.debug("SNMP WALK error: %s", error_indication)
                break
            
            if error_status:
                _LOGGER.debug("SNMP WALK error status: %s", error_status.prettyPrint())
                break

            for var_bind in var_binds:
                oid, value = var_bind
                oid_str = str(oid)
                # Double-check we are still in the tree (walkCmd handles this but good for safety)
                if not oid_str.startswith(base_oid):
                    return results
                results[oid_str] = value.prettyPrint()

    except Exception as exc:
        _LOGGER.debug("SNMP WALK failed on %s (%s): %s", host, base_oid, exc)

    finally:
        if transport:
            try:
                await transport.close()
            except Exception:
                pass

    _LOGGER.debug("SNMP WALK %s -> %d entries", base_oid, len(results))
    return results



async def async_snmp_bulk(
    hass,
    host: str,
    community: str,
    oid_list: list[str],
    timeout: int = 8,
    retries: int = 2,
    mp_model: MpModel = 1,
) -> Dict[str, str | None]:
    """Fast parallel GET for system OIDs."""
    if not oid_list:
        return {}

    async def _get_one(oid: str):
        return await async_snmp_get(
            hass, host, community, oid,
            timeout=timeout, retries=retries, mp_model=mp_model
        )

    results = await asyncio.gather(*[_get_one(oid) for oid in oid_list])
    return dict(zip(oid_list, results))

async def discover_physical_ports(
    hass,
    host: str,
    community: str,
    mp_model: int = SNMP_VERSION_TO_MP_MODEL["v2c"],
) -> dict[int, dict[str, Any]]:
    """
    Auto-discover real physical ports and classify copper vs SFP.

    Returns:
        {
            1: {"if_index": 17, "name": "eth1", "is_copper": True,  "is_sfp": False},
            2: {"if_index": 18, "name": "eth2", "is_copper": True,  "is_sfp": False},
            ...
            25: {"if_index": 101, "name": "Port 25", "is_copper": False, "is_sfp": True},
        }
    """
    mapping: dict[int, dict[str, Any]] = {}
    logical_port = 1

    try:
        # Step 1: Get all interface descriptions
        descr_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.2", mp_model=mp_model
        )
        if not descr_data:
            _LOGGER.debug("discover_physical_ports: no ifDescr data from %s", host)
            return {}

        # Step 2: Get all interface types (for copper vs SFP detection)
        type_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.3", mp_model=mp_model
        )

        for oid_str, descr_raw in descr_data.items():
            try:
                if_index = int(oid_str.split(".")[-1])
                descr = descr_raw.strip().lower()
            except (ValueError, IndexError, AttributeError):
                continue

            # Filter: only real Ethernet ports
            if not any(p in descr for p in ["eth", "ge-", "gigabit", "fasteth", "port ", "lan", "wan"]):
                continue

            # Reject virtual/junk interfaces
            if any(bad in descr for bad in ["br", "vlan", "tun", "lo", "dummy", "wlan", "ath", "rai", "wifi", "wl", "bond", "veth"]):
                continue

            # Get ifType to detect SFP
            type_oid = f"1.3.6.1.2.1.2.2.1.3.{if_index}"
            raw_type = type_data.get(type_oid, "0")
            try:
                if_type = int(raw_type)
            except (ValueError, TypeError):
                if_type = 0

            # Known SFP types (standard + vendor quirks)
            is_sfp = if_type in (
                56,   # fibreChannel (common)
                161,  # optical
                171,  # optical (QNAP, Zyxel)
                172,  # optical (some Cisco)
                117,  # gigabitEthernet (sometimes SFP on cheap switches)
            )
            is_copper = not is_sfp

            # Friendly name
            name = descr_raw.strip()
            if name.lower().startswith("eth"):
                name = f"LAN Port {logical_port}"
            elif "wan" in name.lower():
                name = "WAN"

            mapping[logical_port] = {
                "if_index": if_index,
                "name": name,
                "if_descr": descr_raw.strip(),
                "is_sfp": is_sfp,
                "is_copper": is_copper,
            }
            logical_port += 1

        _LOGGER.info(
            "Auto-discovered %d physical ports on %s (%d copper, %d SFP)",
            len(mapping),
            host,
            sum(1 for p in mapping.values() if p["is_copper"]),
            sum(1 for p in mapping.values() if p["is_sfp"]),
        )
        return mapping

    except asyncio.CancelledError:  # pragma: no cover
        raise

    # ruff: noqa: BLE001
    except Exception as exc:  # intentional broad catch – discovery must not kill integration
        _LOGGER.debug("Failed to auto-discover ports on %s: %s", host, exc)
        return {}
