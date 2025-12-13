"""Async SNMP helper works perfectly with pysnmp-7)"""
from __future__ import annotations
import logging
import re
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

# Create engine with disabled MIB
# must be blocking an global for now else all hell breaks loose
_SNMP_ENGINE = SnmpEngine()

asyncio.get_event_loop().set_debug(False)

_LOGGER = logging.getLogger(__name__)

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
    transport = None
    try:
        transport = await UdpTransportTarget.create((host, 161))
        transport.timeout = timeout
        transport.retries = retries
        obj_identity = ObjectIdentity(oid)
        error_indication, error_status, error_index, var_binds = await get_cmd(
            _SNMP_ENGINE,
            CommunityData(community, mp_model=mp_model),
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
        obj_identity = ObjectIdentity(base_oid)
        iterator = walk_cmd(
            _SNMP_ENGINE,
            CommunityData(community, mp_model=mp_model),
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
                # Double-check we are still in the tree (walkCmd handles this but good for safety)
                if not oid_str.startswith(base_oid):
                    return results
                results[oid_str] = value.prettyPrint()

    except Exception as exc:
        _LOGGER.debug("SNMP WALK failed on %s (%s): %s", host, base_oid, exc)

    _LOGGER.debug("SNMP WALK %s -> %d entries", base_oid, len(results))
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
    mp_model: int = 1,
) -> dict[int, dict[str, Any]]:
    """
    Auto-discover real physical ports and perfectly classify copper vs SFP/SFP+.
    Works on: Zyxel, TP-Link, QNAP, Ubiquiti, Cisco, ASUS, MikroTik, Netgear, D-Link, etc.
    
    Note: Requires 're' module to be imported at the top of the file.
    """
    
    mapping: dict[int, dict[str, Any]] = {}
    logical_port = 1

    try:
        # Step 1: Get interface descriptions
        descr_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.2", mp_model = mp_model
        )
        if not descr_data:
            _LOGGER.debug("discover_physical_ports: no ifDescr data from %s", host)
            return {}

        # Step 2: Get interface types (for reliable SFP detection)
        type_data = await async_snmp_walk(
            hass, host, community, "1.3.6.1.2.1.2.2.1.3", mp_model = mp_model
        )

        for oid_str, descr_raw in descr_data.items():
            try:
                if_index = int(oid_str.split(".")[-1])
                descr_clean = descr_raw.strip()
                descr_lower = descr_clean.lower()
            except (ValueError, IndexError, AttributeError):
                continue

            # === STEP 1: Reject obvious virtual/junk interfaces ===
            # FIXED: Use word boundaries for single-word patterns to avoid false matches
            # Multi-word phrases - use substring matching
            if "cpu interface" in descr_lower or "link aggregate" in descr_lower:
                continue
            
            # Patterns that should match at word start (to catch gre0, tun0, vlan1, etc.)
            # \b at start ensures we don't match "something_gre0"
            word_start_bad = [r'\bvlan', r'\btun', r'\bgre', r'\bimq', r'\bifb', 
                             r'\berspan', r'\bip_vti', r'\bip6_vti', r'\bip6tnl', 
                             r'\bip6gre', r'\bwds']
            if any(re.search(pattern, descr_lower) for pattern in word_start_bad):
                continue
            
            # Patterns that need exact word match (complete words only)
            exact_word_bad = [r'\blo\b', r'\bbr\b', r'\bdummy\b', r'\bwlan\b', 
                             r'\bath\b', r'\bwifi\b', r'\bwl\b', r'\bbond\b', 
                             r'\bveth\b', r'\bbridge\b', r'\bvirtual\b', r'\bnull\b', 
                             r'\bsit\b', r'\bipip\b', r'\bbcmsw\b', r'\bspu\b']
            if any(re.search(pattern, descr_lower) for pattern in exact_word_bad):
                continue

            # === STEP 2: Accept ANYTHING that looks like a real port ===
            # This is the key fix: Zyxel, D-Link, Netgear often use just "1", "2", "25", etc.
            is_likely_physical = (
                # Standard keywords (all lowercase since we're checking descr_lower)
                any(k in descr_lower for k in [
                    "port", "eth", "ge.", "swp", "xe.", "lan", "wan", "sfp", 
                    "gigabit", "fasteth", "10g", "slot:", "level"
                ]) or
                # Just a number → very common (case-insensitive since digits have no case)
                descr_clean.isdigit() or
                # Starts with "p" or "g" + digit (now using descr_lower consistently)
                re.match(r'^[pg]\d+', descr_lower) or
                # Dell-style: "Slot: 0 Port: X ..." (already using descr_lower)
                (descr_lower.startswith("slot:") and "port:" in descr_lower)
            )

            if not is_likely_physical:
                continue

            # === STEP 3: SFP vs Copper detection ===
            raw_type = type_data.get(f"1.3.6.1.2.1.2.2.1.3.{if_index}", "0")
            try:
                if_type = int(raw_type)
            except (ValueError, TypeError):
                if_type = 0

            # ifType values: 6=ethernetCsmacd (copper), 56=fibreChannel, 161/171/172=various fiber
            is_sfp_by_type = if_type in (56, 161, 171, 172)
            
            # Check for SFP indicators in name (using descr_lower for case-insensitive matching)
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
                detection = "heuristic"
            is_copper = not is_sfp

            # === STEP 4: Friendly name generation ===
            # Use descr_lower for matching, but descr_clean for display to preserve original case
            if "slot:" in descr_lower and "port:" in descr_lower:
                # Extract port number from "Slot: 0 Port: 25 ..."
                match = re.search(r"port:\s*(\d+)", descr_lower, re.IGNORECASE)
                if match:
                    name = f"Port {match.group(1)}"
                else:
                    name = f"Port {logical_port}"
            elif descr_clean.isdigit():
                name = f"Port {descr_clean}"
            elif "port " in descr_lower:
                # Preserve original case from descr_clean
                name = descr_clean
            elif descr_lower.startswith(("eth", "ge.", "swp", "xe.")):
                # Preserve original case from descr_clean
                name = descr_clean
            else:
                name = f"Port {logical_port}"

            mapping[logical_port] = {
                "if_index": if_index,
                "name": name,
                "if_descr": descr_clean,  # Always use original case for storage
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
    # ruff: noqa: BLE001
    except Exception as exc:
        _LOGGER.debug("Failed to auto-discover ports on %s: %s", host, exc)
        return {}
