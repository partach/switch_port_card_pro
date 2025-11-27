"""
Async SNMP helper for Switch Port Card Pro.
Fully non-blocking and Home Assistant safe.
"""

from __future__ import annotations
import asyncio
import logging

#for now due to architecture change we focus on supporting v2c only (getcmd is shifted to v1arch)
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

# Global SNMP engine: safe to reuse across calls
SNMP_ENGINE = SnmpEngine()
MpModel = Literal[0, 1]  # 0 = v1, 1 = v2c

async def async_snmp_get(
    hass,
    host: str,
    community: str,
    oid: str,
    timeout: int = 3,
    retries: int = 1,
    mp_model: MpModel = 1,
) -> str | None:
    try:
        response = await asyncio.wait_for(
            getCmd(
                _SNMP_ENGINE,
                CommunityData(community, mpModel=mp_model),
                UdpTransportTarget((host, 161), timeout=timeout, retries=retries),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            ),
            timeout=timeout + 2,
        )
    except asyncio.TimeoutError:
        raise ConnectionError(f"Timeout contacting {host}")
    except Exception as exc:
        raise ConnectionError(f"SNMP error: {exc}")

    error_indication, error_status, error_index, var_binds = response

    if error_indication:
        raise ConnectionError(str(error_indication))
    if error_status:
        raise ValueError(f"{error_status.prettyPrint()} at {error_index}")

    return var_binds[0][1].prettyPrint() if var_binds else None


async def async_snmp_walk(
    hass,
    host: str,
    community: str,
    base_oid: str,
    timeout: int = 3,
    retries: int = 1,
    mp_model: MpModel = 1,
) -> dict[str, str]:
    """Async SNMP WALK v1arch style."""
    results: dict[str, str] = {}

    try:
        async for error_indication, error_status, error_index, var_binds in nextCmd(
            _SNMP_ENGINE,
            CommunityData(community, mpModel=mp_model),
            UdpTransportTarget((host, 161), timeout=timeout, retries=retries),
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
        ):
            if error_indication:
                raise ConnectionError(str(error_indication))
            if error_status:
                raise ValueError(f"{error_status.prettyPrint()} at {error_index}")
            for var_bind in var_binds:
                oid, value = var_bind
                results[str(oid)] = value.prettyPrint()
    except asyncio.TimeoutError:
        raise ConnectionError(f"Walk timeout on {host}")
    except Exception as exc:
        raise ConnectionError(f"Walk failed: {exc}")

    return results


async def async_snmp_bulk(
    hass,
    host: str,
    community: str,
    oid_list: list[str],
    timeout: int = 3,
    retries: int = 1,
) -> dict[str, str]:
    """
    Perform multiple SNMP GETs efficiently.
    Returns {oid: value}.
    """

    tasks = [
        async_snmp_get(hass, host, community, oid, timeout=timeout, retries=retries)
        for oid in oid_list
    ]

    # run all queries concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    mapped = {}
    for oid, result in zip(oid_list, results):
        if isinstance(result, Exception):
            mapped[oid] = None
        else:
            mapped[oid] = result

    return mapped
