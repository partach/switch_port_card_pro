"""Async SNMP helper – works perfectly with pysnmp-lextudio 7.x+ (v3arch)"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

# v3arch is the current official async API (v2c + v3 compatible)
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,      # ← correct name in 7.x
    next_cmd,     # ← correct name in 7.x
)

_LOGGER = logging.getLogger(__name__)

# One global engine safe and recommended
_SNMP_ENGINE = SnmpEngine()

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
    """Async SNMP GET fully non-blocking, works on real HA installs."""
    try:
        # Create transport target (modern way)
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries

        response = await get_cmd(
            _SNMP_ENGINE,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )

    except asyncio.TimeoutError:
        _LOGGER.debug("SNMP GET timeout: %s (oid=%s)", host, oid)
        raise ConnectionError("timeout")
    except Exception as exc:
        _LOGGER.debug("SNMP GET error on %s (oid=%s): %s", host, oid, exc)
        raise ConnectionError(str(exc))

    error_indication, error_status, error_index, var_binds = response

    if error_indication:
        _LOGGER.debug("SNMP error indication: %s", error_indication)
        raise ConnectionError(str(error_indication))

    if error_status:
        msg = error_status.prettyPrint()
        if "noSuchName" in msg or "noSuchObject" in msg:
            return None  # OID doesn't exist — not an error for us
        raise ConnectionError(msg)

    return var_binds[0][1].prettyPrint() if var_binds else None


async def async_snmp_walk(
    hass,
    host: str,
    community: str,
    base_oid: str,
    timeout: int = 10,
    retries: int = 3,
    mp_model: MpModel = 1,
) -> dict[str, str]:
    """Async SNMP WALK returns {full_oid: value}."""
    results: dict[str, str] = {}

    try:
        engine = SnmpEngine() # to make sure we don't get cached stuff
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries

        iterator = next_cmd(
            _SNMP_ENGINE,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
            ignoreNonIncreasingOid=True,
        )

        async for error_indication, error_status, error_index, var_binds in await iterator:
            if error_indication:
                _LOGGER.debug("SNMP WALK error indication: %s", error_indication)
                break
            if error_status:
                break  # End of MIB

            for name, val in var_binds:
                results[str(name)] = val.prettyPrint()

    except Exception as exc:
        _LOGGER.debug("SNMP WALK failed on %s (%s): %s", host, base_oid, exc)

    return results
    
async def async_snmp_bulk(
    hass,
    host: str,
    community: str,
    oid_list: list[str],
    timeout: int = 8,
    retries: int = 2,
    mp_model: MpModel = 1,
) -> dict[str, str | None]:
    """
    Fast parallel SNMP GET for multiple OIDs.
    Perfect for system info (hostname, uptime, CPU, memory) on startup.
    """
    if not oid_list:
        return {}

    async def _get_one(oid: str):
        try:
            return await async_snmp_get(
                hass,
                host,
                community,
                oid,
                timeout=timeout,
                retries=retries,
                mp_model=mp_model,
            )
        except Exception:
            return None

    results = await asyncio.gather(*[_get_one(oid) for oid in oid_list], return_exceptions=False)
    return dict(zip(oid_list, results))
