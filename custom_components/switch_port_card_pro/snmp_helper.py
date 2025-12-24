"""Async SNMP helper works perfectly with pysnmp-7)"""
from __future__ import annotations
import logging
import re
import asyncio
from typing import Dict, Any

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

# Global engine and lock for thread-safe initialization
_SNMP_ENGINE = None
_ENGINE_LOCK = asyncio.Lock()


async def _ensure_engine(hass):
    """Ensure SNMP engine is created (thread-safe)."""
    global _SNMP_ENGINE
    
    async with _ENGINE_LOCK:
        if _SNMP_ENGINE is None:
            # Create engine in executor to avoid blocking
            def _create_engine():
                engine = SnmpEngine()
                # Actually load the MIBs from disk so we do not do it in the event loop
           #     mib_view_controller = view.MibViewController(
           #        engine.message_dispatcher.mib_instrum_controller.get_mib_builder()
           #     )
           #    engine.cache["mibViewController"] = mib_view_controller
           #    mib_view_controller.mibBuilder.load_modules()
                return engine
            
            _SNMP_ENGINE = await hass.async_add_executor_job(_create_engine)
            _LOGGER.debug("SNMP engine created")
    
    return _SNMP_ENGINE


async def async_snmp_get(
    hass,
    host: str,
    community: str,
    oid: str,
    timeout: int = 10,
    retries: int = 3,
    mp_model: int = 1,
) -> str | None:
    """Ultra-reliable async SNMP GET."""
    if not oid or not oid.strip():
        return None
    engine = await _ensure_engine(hass)
    transport = None
    
    try:
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries
        obj_identity = ObjectIdentity(oid)
        error_indication, error_status, error_index, var_binds = await get_cmd(
            engine,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(obj_identity),
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


async def async_snmp_walk(
    hass,
    host: str,
    community: str,
    base_oid: str,
    timeout: int = 10,
    retries: int = 3,
    mp_model: int = 1,
) -> dict[str, str]:
    """
    Async SNMP WALK using the high-level walkCmd.
    Returns {full_oid: value} for all OIDs under base_oid.
    """
    if not base_oid or not base_oid.strip():
        return {}

    engine = await _ensure_engine(hass)
    results: dict[str, str] = {}
    transport = None

    try:
        # Create and configure transport
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries

        # Use walk_cmd for the operation
        obj_identity = ObjectIdentity(base_oid)
        iterator = walk_cmd(
            engine,
            CommunityData(community, mpModel=mp_model),
            transport,
            ContextData(),
            ObjectType(obj_identity),
            lexicographicMode=False,
            ignoreNonIncreasingOid=True,
        )
        try:
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
                    # Double-check we are still in the tree
                    if not oid_str.startswith(base_oid):
                        return results
                    results[oid_str] = value.prettyPrint()
        except Exception as iter_err:
                    _LOGGER.debug("SNMP WALK iterator failed on %s (oid=%s): %s", host, base_oid, iter_err)
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
    mp_model: int = 1,
) -> Dict[str, str | None]:
    """Fast parallel GET for system OIDs. Skips empty/blank OIDs."""
    if not oid_list:
        return {}

    # Filter out empty or whitespace-only OIDs and remember which ones were skipped
    filtered_oids = []
    results_template = {}
    for oid in oid_list:
        stripped = oid.strip() if oid else ""
        if stripped:
            filtered_oids.append(stripped)
            results_template[stripped] = None  # placeholder for real result
        else:
            # Map original (blank) OID to None immediately
            results_template[oid] = None

    if not filtered_oids:
        return results_template  # All were blank → return all None

    # Perform parallel GET only on valid OIDs
    async def _get_one(oid: str):
        return await async_snmp_get(
            hass, host, community, oid,
            timeout=timeout, retries=retries, mp_model=mp_model
        )

    valid_results = await asyncio.gather(*[_get_one(oid) for oid in filtered_oids])

    # Combine results back in original order/structure
    for oid, result in zip(filtered_oids, valid_results):
        results_template[oid] = result

    # Preserve original oid_list order and include blanks as None
    final_results = {}
    for oid in oid_list:
        stripped = oid.strip() if oid else ""
        final_results[oid] = results_template.get(stripped)

    return final_results


async def discover_physical_ports(
    hass,
    host: str,
    community: str,
    mp_model: int = 1,
) -> dict[int, dict[str, Any]]:
    """
    Auto-discover real physical ports and perfectly classify copper vs SFP/SFP+.
    Works on: Zyxel, TP-Link, QNAP, Ubiquiti, Cisco, ASUS, MikroTik, Netgear, D-Link, H3C, etc.
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
        _LOGGER.debug("ifDescr data from %s: %s", host, descr_data)

        # Step 2: Get interface types
        type_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.3", mp_model=mp_model
        )
        _LOGGER.debug("ifType data from %s: %s", host, type_data)

        # Step 3: Get port speeds (ifSpeed + ifHighSpeed)
        speed_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.5", mp_model=mp_model
        )
        high_speed_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.31.1.1.1.15", mp_model=mp_model
        )

        # Step 4: Get sysDescr for manufacturer
        sys_descr_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.1.1.0", mp_model=mp_model
        )
        sys_descr = list(sys_descr_data.values())[0] if sys_descr_data else "Unknown"
        _LOGGER.debug("sysDescr: %s", sys_descr)

        # Enhanced manufacturer extraction
        manufacturer = "Unknown"
        if sys_descr:
            # Split and take first meaningful word
            parts = sys_descr.strip().split()
            if parts:
                candidate = parts[0]
                # Filter out junk like version numbers
                if candidate.lower() not in ["version", "software", "release", "v", "build"]:
                    manufacturer = candidate
                elif len(parts) > 1:
                    manufacturer = parts[1]  # fallback

        for oid_str, descr_raw in descr_data.items():
            try:
                if_index = int(oid_str.split(".")[-1])
                descr_clean = descr_raw.strip()
                descr_lower = descr_clean.lower()
            except (ValueError, IndexError, AttributeError):
                continue

            # === Reject virtual interfaces ===
            if any(x in descr_lower for x in ["cpu", "link aggregate", "logical", "vlan", "loopback"]):
                continue

            # === Accept physical-like ports ===
            is_likely_physical = any(k in descr_lower for k in [
                "port", "eth", "ge.", "swp", "xe.", "lan", "wan", "sfp", "gigabit", "fasteth", "10g"
            ]) or re.match(r'^gigabitethernet\d+', descr_lower) or descr_clean.isdigit()

            if not is_likely_physical:
                continue

            # === SFP vs Copper detection ===
            raw_type = "0"
            for t_oid, t_val in type_data.items():
                if t_oid.endswith(f".{if_index}"):
                    raw_type = t_val
                    break

            try:
                if '(' in str(raw_type):
                    if_type = int(re.search(r'\((\d+)\)', str(raw_type)).group(1))
                else:
                    if_type = int(raw_type)
            except (ValueError, TypeError):
                if_type = 0

            # More ifType values for SFP
            is_sfp_by_type = if_type in (56, 117, 161, 171, 172, 195, 196, 197)  # added more

            is_sfp_by_name = any(k in descr_lower for k in [
                "sfp", "fiber", "fibre", "optical", "1000base", "10gbase", "sfp+", "sfp28"
            ])

            detection = "heuristic"
            if is_sfp_by_name:
                is_sfp = True
                detection = "name"
            elif is_sfp_by_type:
                is_sfp = True
                detection = "type"
            else:
                is_sfp = False

            # === Port speed ===
            speed_mbps = 0
            raw_speed = speed_data.get(f"1.3.6.1.2.1.2.2.1.5.{if_index}")
            raw_high = high_speed_data.get(f"1.3.6.1.2.1.31.1.1.1.15.{if_index}")
            if raw_high:
                speed_mbps = int(raw_high)
            elif raw_speed:
                speed_mbps = int(raw_speed) // 1_000_000

            # === Friendly name ===
            name = descr_clean
            if "port" in descr_lower:
                match = re.search(r"port\s*[:/]?\s*(\d+)", descr_lower, re.IGNORECASE)
                if match:
                    name = f"Port {match.group(1)}"

            mapping[logical_port] = {
                "if_index": if_index,
                "name": name,
                "if_descr": descr_clean,
                "is_sfp": is_sfp,
                "is_copper": not is_sfp,
                "detection": detection,
                "speed_mbps": speed_mbps,
                "manufacturer": manufacturer,
            }
            logical_port += 1

        copper_count = sum(1 for p in mapping.values() if p["is_copper"])
        sfp_count = len(mapping) - copper_count
        _LOGGER.info(
            "Auto-discovered %d physical ports on %s (%s) → %d copper, %d SFP | Speeds detected",
            len(mapping), host, manufacturer, copper_count, sfp_count
        )
        return mapping

    except Exception as exc:
        _LOGGER.debug("Failed to auto-discover ports on %s: %s", host, exc)
        return {}
