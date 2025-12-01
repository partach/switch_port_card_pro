"""Async SNMP helper – works perfectly with pysnmp-lextudio 7.x+ (v3arch)"""
from __future__ import annotations
import logging
import asyncio
from typing import Literal, Dict, Any

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

from .const import SNMP_VERSION_TO_MP_MODEL

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
            ObjectType(ObjectIdentity(oid).resolveWithMib(False)),
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
            ObjectType(ObjectIdentity(base_oid).resolveWithMib(False)),
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
    Auto-discover real physical ports and perfectly classify copper vs SFP/SFP+.
    Works on Zyxel, TP-Link, QNAP, Ubiquiti, Cisco, ASUS, and more.
    """
    mapping: dict[int, dict[str, Any]] = {}
    logical_port = 1

    try:
        # Step 1: Get interface descriptions
        descr_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.2", mp_model=mp_model
        )
        if not descr_data:
            _LOGGER.debug("discover_physical_ports: no ifDescr data from %s", host)
            return {}

        # Step  # Step 2: Get interface types (for ifType-based SFP detection)
        type_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.3", mp_model=mp_model
        )

        for oid_str, descr_raw in descr_data.items():
            try:
                if_index = int(oid_str.split(".")[-1])
                descr_lower = descr_raw.strip().lower()
                descr_clean = descr_raw.strip()
            except (ValueError, IndexError, AttributeError):
                continue

            # Filter: only real physical Ethernet ports
            if not any(p in descr_lower for p in ["eth", "ge-", "gigabit", "fasteth", "port ", "lan", "wan"]):
                continue

            # Reject virtual/junk interfaces
            if any(bad in descr_lower for bad in ["br", "vlan", "tun", "lo", "dummy", "wlan", "ath", "rai", "wifi", "wl", "bond", "veth", "bridge", "virtual"]):
                continue

            # === UNIVERSAL SFP DETECTION (ifType + name) ===
            raw_type = type_data.get(f"1.3.6.1.2.1.2.2.1.3.{if_index}", "0")
            try:
                if_type = int(raw_type)
            except (ValueError, TypeError):
                if_type = 0

            # Method 1: Known fiber ifTypes
            is_sfp_by_type = if_type in (56, 161, 171, 172, 117)

            # Method 2: Name contains SFP/fiber keywords (Zyxel, TP-Link, QNAP, etc.)
            is_sfp_by_name = any(
                keyword in descr_lower for keyword in [
                    "sfp", "fiber", "optical", "1000base-x", "10gbase", "mini-gbic", "sfp+", "sfp28"
                ]
            )

            # Final verdict
            is_sfp = is_sfp_by_type or is_sfp_by_name
            is_copper = not is_sfp

            # Friendly name — keep the real name on routers, make it pretty on switches
            if descr_lower.startswith("eth") or descr_lower.startswith("ge"):
                # ASUS, TP-Link routers — keep original name (eth1, eth2, etc.)
                name = descr_clean
            elif "port " in descr_lower or "lan" in descr_lower:
                # Managed switches (Zyxel, QNAP) — use the clean description
                name = descr_clean
            else:
                # Fallback
                name = f"Port {logical_port}"

            mapping[logical_port] = {
                "if_index": if_index,
                "name": name,
                "if_descr": descr_clean,
                "is_sfp": is_sfp,
                "is_copper": is_copper,
            }
            logical_port += 1

        copper_count = sum(1 for p in mapping.values() if p["is_copper"])
        sfp_count = sum(1 for p in mapping.values() if p["is_sfp"])

        _LOGGER.info(
            "Auto-discovered %d physical ports on %s → %d copper, %d SFP/SFP+",
            len(mapping), host, copper_count, sfp_count
        )
        return mapping

    except asyncio.CancelledError:  # pragma: no cover
        raise

    # ruff: noqa: BLE001
    except Exception as exc:  # intentional — discovery must never crash the integration
        _LOGGER.debug("Failed to auto-discover ports on %s: %s", host, exc)
        return {}
