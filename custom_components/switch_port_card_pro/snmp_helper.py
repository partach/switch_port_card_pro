"""Async SNMP helper works perfectly with pysnmp-7"""
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
from .const import (
    CONF_OID_IDESCR,
    CONF_OID_IFTYPE,
    CONF_OID_IFSPEED,
    CONF_OID_IFHIGHSPEED,
    CONF_OID_SYSDESCR,
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
    snmp_port: int,
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
        transport = await UdpTransportTarget.create((host, snmp_port))
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

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _LOGGER.debug("SNMP GET exception on %s (oid=%s): %s", host, oid, exc)
        return None


async def async_snmp_walk(
    hass,
    host: str,
    community: str,
    snmp_port: int,
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
        transport = await UdpTransportTarget.create((host, snmp_port))
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
        except asyncio.CancelledError:
            raise
        except Exception as iter_err:
            _LOGGER.debug("SNMP WALK iterator failed on %s (oid=%s): %s", host, base_oid, iter_err)
    
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _LOGGER.debug("SNMP WALK failed on %s (%s): %s", host, base_oid, exc)
    
    return results


async def async_snmp_bulk(
    hass,
    host: str,
    community: str,
    snmp_port: int,
    oid_list: list[str],
    timeout: int = 8,
    retries: int = 2,
    mp_model: int = 1,
) -> Dict[str, str | None]:
    """Fast parallel GET for system OIDs. Skips empty/blank OIDs."""
    if not oid_list:
        return {}

    # Filter out empty or whitespace-only OIDs
    filtered_oids = []
    results_template = {}
    for oid in oid_list:
        stripped = oid.strip() if oid else ""
        if stripped:
            filtered_oids.append(stripped)
            results_template[stripped] = None
        else:
            results_template[oid] = None

    if not filtered_oids:
        return results_template

    # Perform parallel GET only on valid OIDs
    async def _get_one(oid: str):
        return await async_snmp_get(
            hass, host, community, snmp_port, oid,
            timeout=timeout, retries=retries, mp_model=mp_model
        )

    valid_results = await asyncio.gather(*[_get_one(oid) for oid in filtered_oids])

    # Combine results back
    for oid, result in zip(filtered_oids, valid_results):
        results_template[oid] = result

    # Preserve original oid_list order
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
            hass, host, community, snmp_port, CONF_OID_IDESCR, mp_model=mp_model
        )
        if not descr_data:
            _LOGGER.debug("discover_physical_ports: no ifDescr data from %s", host)
            return {}
        
        _LOGGER.debug("ifDescr data from %s: %d interfaces found", host, len(descr_data))
        
        # Step 2: Get interface types (for reliable SFP detection)
        type_data = await async_snmp_walk(
            hass, host, community, snmp_port, CONF_OID_IFTYPE, mp_model=mp_model
        )
        _LOGGER.debug("ifType data from %s: %d types found", host, len(type_data))
        
        # Step 3: Get speed data
        speed_data = await async_snmp_walk(
            hass, host, community, snmp_port, CONF_OID_IFSPEED, mp_model=mp_model
        )
        high_speed_data = await async_snmp_walk(
            hass, host, community, snmp_port, CONF_OID_IFHIGHSPEED, mp_model=mp_model
        )
        
        # Step 4: Get sysDescr for manufacturer info
        sys_descr_data = await async_snmp_walk(
            hass, host, community, snmp_port, CONF_OID_SYSDESCR, mp_model=mp_model
        )
        sys_descr = list(sys_descr_data.values())[0] if sys_descr_data else "Unknown"
        _LOGGER.debug("sysDescr from %s: %s", host, sys_descr)
        
        # Extract manufacturer from sysDescr
        manufacturer = _extract_manufacturer(sys_descr)
        
        sorted_oids = sorted(descr_data.keys(), key=lambda x: int(x.split('.')[-1]))
        for oid_str in sorted_oids:
            descr_raw = descr_data[oid_str]
            try:
                # Extract ifIndex from the end of the OID
                if_index = int(oid_str.split(".")[-1])
                descr_clean = descr_raw.strip()
                descr_lower = descr_clean.lower()
            except (ValueError, IndexError, AttributeError):
                continue
            
            # === STEP 1: Reject obvious virtual/junk interfaces ===
            if _is_virtual_interface(descr_lower):
                continue
            
            # === STEP 2: Accept anything that looks like a real port ===
            is_likely_physical = _is_physical_interface(descr_lower, descr_clean, if_index)
            
            if not is_likely_physical:
                continue
            
            # === STEP 3: SFP vs Copper detection ===
            if_type = _get_interface_type(type_data, if_index)
            is_sfp, detection = _detect_sfp_port(if_type, descr_lower)
            is_copper = not is_sfp
            
            # === STEP 4: Port speed ===
            speed_mbps = _get_port_speed(speed_data, high_speed_data, if_index)
            
            # === STEP 5: Friendly name generation ===
            name = _generate_port_name(descr_clean, descr_lower, logical_port)
            
            mapping[logical_port] = {
                "if_index": if_index,
                "name": name,
                "if_descr": descr_clean,
                "is_sfp": is_sfp,
                "is_copper": is_copper,
                "detection": detection,
                "speed_mbps": speed_mbps,
                "manufacturer": manufacturer,
            }
            logical_port += 1
        
        copper_count = sum(1 for p in mapping.values() if p["is_copper"])
        sfp_count = len(mapping) - copper_count
        _LOGGER.info(
            "Auto-discovered %d physical ports on %s → %d copper, %d SFP/SFP+ | Manufacturer: %s",
            len(mapping), host, copper_count, sfp_count, manufacturer
        )
        return mapping
        
    except asyncio.CancelledError:
        raise
    except Exception:
        _LOGGER.exception("Failed to auto-discover ports on %s", host)
        return {}


def _extract_manufacturer(sys_descr: str) -> str:
    """Extract manufacturer name from sysDescr string."""
    if not sys_descr or sys_descr == "Unknown":
        return "Unknown"
    
    # Common patterns: "H3C S3100-26C, Software Version..." → "H3C"
    first_word = sys_descr.split(" ")[0]
    
    # Reject common non-manufacturer words
    if first_word.lower() in ("version", "software", "hardware", "release", "build"):
        return "Unknown"
    
    return first_word


def _is_virtual_interface(descr_lower: str) -> bool:
    """Check if interface description indicates a virtual interface."""
    # Quick rejections first
    if any(x in descr_lower for x in ["cpu interface", "link aggregate", "logical-int"]):
        return True
    
    # Patterns that should match at word start
    word_start_bad = [
        r'\bvlan', r'\btun', r'\bgre', r'\bimq', r'\bifb',
        r'\berspan', r'\bip_vti', r'\bip6_vti', r'\bip6tnl',
        r'\bip6gre', r'\bwds', r'\bloopback', r'\bpo\d+'
    ]
    if any(re.search(pattern, descr_lower) for pattern in word_start_bad):
        return True
    
    # Patterns that need exact word match
    exact_word_bad = [
        r'\blo\b', r'\bbr\b', r'\bdummy\b', r'\bwlan\b',
        r'\bath\b', r'\bwifi\b', r'\bwl\b', r'\bbond\b',
        r'\bveth\b', r'\bbridge\b', r'\bvirtual\b', r'\bnull\b',
        r'\bsit\b', r'\bipip\b', r'\bbcmsw\b', r'\bspu\b'
    ]
    return any(re.search(pattern, descr_lower) for pattern in exact_word_bad)


def _is_physical_interface(descr_lower: str, descr_clean: str, if_index: int) -> bool:
    """Check if interface description indicates a physical interface."""
    # Universal exclusion of management/console ports
    if any(k in descr_lower for k in ["mgmt", "management", "console"]):
        return False
        
    # Specifically catch Cisco/Standard management ports like GigabitEthernet0/0
    if re.search(r'ethernet0/0$', descr_lower):
        return False
    
    # Check for common physical port indicators
    is_likely_physical = (
        any(k in descr_lower for k in [
            "port", "eth", "ge.", "swp", "xe.", "lan", "wan", "sfp",
            "gigabit", "fasteth", "10g", "slot:", "level",
        ]) or
        re.match(r'^gigabithethernet\d+', descr_lower) or
        re.match(r'^[pg]\d+$', descr_lower) or
        (descr_lower.startswith("slot:") and "port:" in descr_lower)
    )
    
    # Special case: single-digit descriptions
    if descr_clean.isdigit():
        if if_index >= 1000:
            return False
        return True
    
    return is_likely_physical


def _get_interface_type(type_data: dict, if_index: int) -> int:
    """Extract interface type from SNMP data."""
    raw_type = "0"
    
    for t_oid, t_val in type_data.items():
        if t_oid.endswith(f".{if_index}"):
            raw_type = t_val
            break
    
    try:
        # Handle types like "ethernetCsmacd(6)"
        if '(' in str(raw_type):
            match_type = re.search(r'\((\d+)\)', str(raw_type))
            return int(match_type.group(1)) if match_type else 0
        return int(raw_type)
    except (ValueError, TypeError):
        return 0

def _detect_sfp_port(if_type: int, descr_lower: str) -> tuple[bool, str]:
    """Detect if port is SFP/fiber based on type and name."""
    # Netgear 10G special case
    if "10g - level" in descr_lower:
        return True, "netgear_10g_sfp"

    # Cisco stack/modular slot logic
    cisco_slot_match = re.search(r'gigabithethernet(\d+)/(\d+)/(\d+)', descr_lower)
    if cisco_slot_match:
        module_slot = int(cisco_slot_match.group(2))
        if module_slot > 0:
            return True, "cisco_module_sfp"
        return False, "cisco_fixed_copper"

    # Standard SNMP types for fiber
    if if_type in (56, 161, 171, 172):
        return True, "type_match"
    
    # Common keyword matching
    is_sfp_by_name = any(k in descr_lower for k in [
        "sfp", "fiber", "fibre", "optical", "1000base-x", "10gbase-", 
        "mini-gbic", "sfp+", "sfp28", "25g", "40g", "100g", "qsfp"
    ])
    
    if is_sfp_by_name or "fortygigabit" in descr_lower:
        return True, "name_keyword"

    return False, "default_copper"

def _get_port_speed(speed_data: dict, high_speed_data: dict, if_index: int) -> int:
    """Get port speed in Mbps."""
    # Try high-speed first (ifHighSpeed)
    raw_high = high_speed_data.get(f"{CONF_OID_IFHIGHSPEED}.{if_index}")
    if raw_high:
        try:
            return int(raw_high)
        except (ValueError, TypeError):
            pass
    
    # Fall back to regular speed (ifSpeed)
    raw_speed = speed_data.get(f"{CONF_OID_IFSPEED}.{if_index}")
    if raw_speed:
        try:
            return int(raw_speed) // 1_000_000
        except (ValueError, TypeError):
            pass
    
    return 0


def _generate_port_name(descr_clean: str, descr_lower: str, logical_port: int) -> str:
    """Generate a friendly port name."""
    # Slot:X Port:Y format
    if "slot:" in descr_lower and "port:" in descr_lower:
        match = re.search(r"port:\s*(\d+)", descr_lower, re.IGNORECASE)
        if match:
            return f"Port {match.group(1)}"
    
    # Pure numeric description
    if descr_clean.isdigit():
        return f"Port {descr_clean}"
    
    # Cisco GigabitEthernet format
    if "gigabithethernet" in descr_lower:
        match = re.search(r'(\d+)$', descr_lower)
        if match:
            return f"Port {match.group(1)}"
        return descr_clean
    
    # Already has "port" in name
    if "port " in descr_lower:
        return descr_clean
    
    # Standard interface names
    if descr_lower.startswith(("eth", "ge.", "swp", "xe.")):
        return descr_clean
    
    # Fallback
    return f"Port {logical_port}"
