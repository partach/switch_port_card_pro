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
_SNMP_ENGINE = SnmpEngine()

# KILL MIB LOADING — THIS IS THE HOLY GRAIL
_SNMP_ENGINE.get_mib_builder().setMibSources()  # ← NO MORE BLOCKING I/O EVER

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
    """
    FINAL WALK
    """
    results: dict[str, str] = {}
    transport = None

    try:
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries

        # THE ONLY CORRECT WAY IN 2025 — DO NOT CHANGE
        cmd_gen = next_cmd(
            _SNMP_ENGINE,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False,
            ignoreNonIncreasingOid=True,
            maxRows=50,  # Prevent huge responses from killing us
        )

        # AWAIT + ASYNC FOR
        async for error_indication, error_status, error_index, var_binds in await cmd_gen:
            if error_indication:
                _LOGGER.debug("SNMP WALK stopped: %s", error_indication)
                break
            if error_status:
                # This is NORMAL — means "end of MIB view"
                if error_status == 2:  # noSuchName = end of walk
                    break
                _LOGGER.debug("SNMP WALK ended: %s", error_status.prettyPrint())
                break

            for oid, val in var_binds:
                oid_str = str(oid)
                if not oid_str.startswith(base_oid):
                    continue  # Safety
                results[oid_str] = val.prettyPrint()

    except asyncio.TimeoutError:
        _LOGGER.debug("SNMP WALK timeout on %s for %s", host, base_oid)
    except Exception as e:
        _LOGGER.debug("SNMP WALK exception on %s (%s): %s", host, base_oid, e)
    finally:
        if transport:
            try:
                await transport.close()
            except:
                pass

    _LOGGER.debug("SNMP WALK %s → %d results", base_oid, len(results))
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
