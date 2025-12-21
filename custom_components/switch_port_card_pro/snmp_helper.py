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
                return SnmpEngine()
            
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
        return None

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
    Works on: Zyxel, TP-Link, QNAP, Ubiquiti, Cisco, ASUS, MikroTik, Netgear, D-Link, etc.
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
        else:
            _LOGGER.debug("ifDescr data from %s with info:\n%s", host, descr_data)

        # Step 2: Get interface types (for reliable SFP detection)
        type_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.3", mp_model=mp_model
        )
        _LOGGER.debug("ifIndex data from %s with info:\n%s", host, type_data)

        for oid_str, descr_raw in descr_data.items():
            try:
                # Extract ifIndex from the end of the OID
                if_index = int(oid_str.split(".")[-1])
                descr_clean = descr_raw.strip()
                descr_lower = descr_clean.lower()
            except (ValueError, IndexError, AttributeError):
                continue


            # === STEP 1: Reject obvious virtual/junk interfaces ===
            if any(x in descr_lower for x in ["cpu interface", "link aggregate", "logical-int"]):
                continue
            
            # Patterns that should match at word start
            word_start_bad = [r'\bvlan', r'\btun', r'\bgre', r'\bimq', r'\bifb', 
                             r'\berspan', r'\bip_vti', r'\bip6_vti', r'\bip6tnl', 
                             r'\bip6gre', r'\bwds', r'\bloopback', r'\bpo\d+']
            if any(re.search(pattern, descr_lower) for pattern in word_start_bad):
                continue
            
            # Patterns that need exact word match
            exact_word_bad = [r'\blo\b', r'\bbr\b', r'\bdummy\b', r'\bwlan\b', 
                             r'\bath\b', r'\bwifi\b', r'\bwl\b', r'\bbond\b', 
                             r'\bveth\b', r'\bbridge\b', r'\bvirtual\b', r'\bnull\b', 
                             r'\bsit\b', r'\bipip\b', r'\bbcmsw\b', r'\bspu\b']
            if any(re.search(pattern, descr_lower) for pattern in exact_word_bad):
                continue

            # === STEP 2: Accept anything that looks like a real port ===
            is_likely_physical = (
                any(k in descr_lower for k in [
                    "port", "eth", "ge.", "swp", "xe.", "lan", "wan", "sfp", 
                    "gigabit", "fasteth", "10g", "slot:", "level",
                ]) or
                re.match(r'^gigabithethernet\d+', descr_lower) or
                re.match(r'^[pg]\d+$', descr_lower) or
                (descr_lower.startswith("slot:") and "port:" in descr_lower)
            )
            # Special case: single-digit descriptions are ambiguous
            # Only accept if ifIndex is reasonable (< 1000) AND no other indicators of virtual
            if descr_clean.isdigit():
                # If it's just a digit and ifIndex is very high, likely virtual
                if if_index >= 1000:
                    continue
                # Otherwise treat as potentially physical
                is_likely_physical = True
            if not is_likely_physical:
                continue

            # === STEP 3: SFP vs Copper detection ===
            # Attempt to find the type for this specific index
            raw_type = "0"
            for t_oid, t_val in type_data.items():
                if t_oid.endswith(f".{if_index}"):
                    raw_type = t_val
                    break
            
            try:
                # Handle types if they come back as strings like "ethernetCsmacd(6)"
                if '(' in str(raw_type):
                    match_type = re.search(r'\((\d+)\)', str(raw_type))
                    if_type = int(match_type.group(1)) if match_type else 0
                else:
                    if_type = int(raw_type)
            except (ValueError, TypeError):
                if_type = 0

            is_sfp_by_type = if_type in (56, 161, 171, 172)
            
            is_sfp_by_name = any(k in descr_lower for k in [
                "sfp", "fiber", "fibre", "optical", "1000base-x", "10gbase", "10g", 
                "mini-gbic", "sfp+", "sfp28"
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
            
            is_copper = not is_sfp

            # === STEP 4: Friendly name generation ===
            if "slot:" in descr_lower and "port:" in descr_lower:
                match = re.search(r"port:\s*(\d+)", descr_lower, re.IGNORECASE)
                name = f"Port {match.group(1)}" if match else f"Port {logical_port}"
            elif descr_clean.isdigit():
                name = f"Port {descr_clean}"
            elif "gigabithethernet" in descr_lower:
                # Cisco extraction: gigabithethernet1 -> Port 1
                match = re.search(r'(\d+)$', descr_lower)
                name = f"Port {match.group(1)}" if match else descr_clean
            elif "port " in descr_lower:
                name = descr_clean
            elif descr_lower.startswith(("eth", "ge.", "swp", "xe.")):
                name = descr_clean
            else:
                name = f"Port {logical_port}"

            mapping[logical_port] = {
                "if_index": if_index,
                "name": name,
                "if_descr": descr_clean,
                "is_sfp": is_sfp,
                "is_copper": is_copper,
                "detection": detection,
            }
            logical_port += 1

        copper_count = sum(1 for p in mapping.values() if p["is_copper"])
        sfp_count = len(mapping) - copper_count
        _LOGGER.info(
            "Auto-discovered %d physical ports on %s → %d copper, %d SFP/SFP+",
            len(mapping), host, copper_count, sfp_count
        )
        return mapping

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _LOGGER.debug("Failed to auto-discover ports on %s: %s", host, exc)
        return {}
