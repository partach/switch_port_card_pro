"""
Async SNMP helper for Switch Port Card Pro.
Fully non-blocking and Home Assistant safe.
"""

from __future__ import annotations
import asyncio
import logging

from pysnmp.hlapi.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    getCmd,
    nextCmd,
    ObjectType,
    ObjectIdentity,
)

_LOGGER = logging.getLogger(__name__)

# Global SNMP engine: safe to reuse across calls
SNMP_ENGINE = SnmpEngine()


async def async_snmp_get(
    hass,
    host: str,
    community: str,
    oid: str,
    timeout: int = 3,
    retries: int = 1,
) -> str:
    """
    Perform an async SNMP GET.
    Raises ConnectionError or ValueError with meaningful messages.
    """

    try:
        response = await asyncio.wait_for(
            getCmd(
                SNMP_ENGINE,
                CommunityData(community),
                UdpTransportTarget((host, 161), timeout=timeout, retries=retries),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            ),
            timeout=timeout + 1,  # wrapper timeout
        )

    except asyncio.TimeoutError:
        raise ConnectionError(f"SNMP timeout contacting {host}")

    except Exception as exc:
        raise ConnectionError(f"SNMP GET failed: {exc}")

    error_indication, error_status, error_index, var_binds = response

    if error_indication:
        raise ConnectionError(f"SNMP engine error: {error_indication}")

    if error_status:
        raise ValueError(
            f"{error_status.prettyPrint()} at index {error_index}"
        )

    return var_binds[0][1].prettyPrint()


async def async_snmp_walk(
    hass,
    host: str,
    community: str,
    oid: str,
    timeout: int = 3,
    retries: int = 1,
) -> dict[str, str]:
    """
    Perform an async SNMP WALK (via nextCmd).
    Returns a dict {oid: value}.
    """

    results: dict[str, str] = {}

    try:
        async for (
            error_indication,
            error_status,
            error_index,
            var_binds,
        ) in nextCmd(
            SNMP_ENGINE,
            CommunityData(community),
            UdpTransportTarget((host, 161), timeout=timeout, retries=retries),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
        ):
            if error_indication:
                raise ConnectionError(error_indication)

            if error_status:
                raise ValueError(f"{error_status.prettyPrint()} at {error_index}")

            for name, val in var_binds:
                results[str(name)] = val.prettyPrint()

    except asyncio.TimeoutError:
        raise ConnectionError(f"SNMP walk timeout contacting {host}")

    except Exception as exc:
        raise ConnectionError(f"SNMP WALK failed: {exc}")

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
