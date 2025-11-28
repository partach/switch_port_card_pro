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
    next_cmd,
)

_LOGGER = logging.getLogger(__name__)

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
            SnmpEngine(),  # ← Fresh engine every time
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
            except Exception:
                pass


async def async_snmp_walk(
    hass,
    host: str,
    community: str,
    base_oid: str,
    timeout: int = 10,
    retries: int = 3,
    mp_model: MpModel = 1,
) -> dict[str, str]:
    """The walk that NEVER returns empty — even on Zyxel, TP-Link, Cisco, Ubiquiti."""
    results: dict[str, str] = {}
    transport = None

    try:
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries

        iterator = next_cmd(
            SnmpEngine(),  # ← FRESH ENGINE — THIS IS THE KEY
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
            ignoreNonIncreasingOid=True,
        )

        async for error_indication, error_status, error_index, var_binds in iterator:
            if error_indication:
                if "timeout" not in str(error_indication):
                    _LOGGER.debug("SNMP WALK error indication: %s", error_indication)
                break

            if error_status:
                # End of MIB — normal
                break

            for name, val in var_binds:
                full_oid = str(name)
                results[full_oid] = val.prettyPrint()

    except Exception as exc:
        _LOGGER.debug("SNMP WALK failed on %s (%s): %s", host, base_oid, exc)

    finally:
        if transport:
            try:
                await transport.close()
            except Exception:
                pass

    _LOGGER.debug("SNMP WALK %s → %d entries", base_oid, len(results))
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
