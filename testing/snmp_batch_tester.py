import re
import sys
import json
import glob
from typing import Dict, Any, List
from pathlib import Path

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
    # Universal exclusion of management/console ports (e.g., Cisco 3850 Gig0/0)
    if any(k in descr_lower for k in ["mgmt", "management", "console"]):
        return False
        
    # Specifically catch Cisco/Standard management ports like GigabitEthernet0/0
    # but allow valid data ports like 1/0/1
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
        # If ifIndex is very high, likely virtual
        if if_index >= 1000:
            return False
        # Otherwise treat as potentially physical
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

    # Cisco stack/modular slot logic (modular slots are typically SFP)
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
    # Try high-speed first (ifHighSpeed - more accurate for Gigabit+)
    raw_high = high_speed_data.get(f"1.3.6.1.2.1.31.1.1.1.15.{if_index}")
    if raw_high:
        try:
            return int(raw_high)
        except (ValueError, TypeError):
            pass
    
    # Fall back to regular speed (ifSpeed)
    raw_speed = speed_data.get(f"1.3.6.1.2.1.2.2.1.5.{if_index}")
    if raw_speed:
        try:
            return int(raw_speed) // 1_000_000
        except (ValueError, TypeError):
            pass
    
    return 0


def _generate_port_name(descr_clean: str, descr_lower: str, logical_port: int) -> str:
    """Generate a friendly port name."""
    # Slot:X Port:Y format (common in enterprise switches)
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
    
    # Standard interface names (eth0, ge.1.1, swp1, xe.0.1)
    if descr_lower.startswith(("eth", "ge.", "swp", "xe.")):
        return descr_clean
    
    # Fallback to logical port number
    return f"Port {logical_port}"


def DoTheLoop(sys_descr: str, descr_data: Dict[str, str], type_data: Dict[str, str]) -> Dict[int, Dict[str, Any]]:
    mapping: Dict[int, Dict[str, Any]] = {}
    logical_port = 1
    manufacturer = _extract_manufacturer(sys_descr)

    # Main Loop: Identify physical ports and map them
    # Sorted by ifIndex to maintain hardware order
    for oid_str in sorted(descr_data.keys(), key=lambda x: int(x.split('.')[-1])):
        descr_raw = descr_data[oid_str]
        try:
            if_index = int(oid_str.split(".")[-1])
            descr_clean, descr_lower = descr_raw.strip(), descr_raw.strip().lower()
        except (ValueError, IndexError):
            continue
        
        # 1. Skip Virtual
        if _is_virtual_interface(descr_lower):
            continue
            
        # 2. Skip non-physical (Management, VLANs, etc.)
        if not _is_physical_interface(descr_lower, descr_clean, if_index):
            continue
        
        # 3. Detect Hardware details
        if_type = _get_interface_type(type_data, if_index)
        is_sfp, detection = _detect_sfp_port(if_type, descr_lower)
        
        mapping[logical_port] = {
            "if_index": if_index,
            "name": _generate_port_name(descr_clean, descr_lower, logical_port),
            "if_descr": descr_clean,
            "is_sfp": is_sfp,
            "is_copper": not is_sfp,
            "detection_method": detection,
            "manufacturer": manufacturer,
        }
        logical_port += 1

    return mapping

def test_discover_physical_ports(filename: str) -> Dict[int, Dict[str, Any]]:
    """Test version of discover_physical_ports reading SNMP from file."""
    descr_data: Dict[str, str] = {}
    type_data: Dict[str, str] = {}
    sys_descr = "Unknown"

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                # Extract SysDescr for manufacturer detection
                if "sysDescr" in line or ".1.3.6.1.2.1.1.1.0" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1: sys_descr = parts[1].strip().strip('"')

                # Regex to handle different dump formats (Standard vs Cisco-style logs)
                match_std = re.match(r'([A-Za-z0-9:\.\-]+)\s*=\s*(\w+):\s*(.*)', line)
                match_cisco = re.match(r'OID=([\d\.\-]+),\s*Type=(\w+),\s*Value=(.*)', line)

                if match_std:
                    oid, val = match_std.group(1), match_std.group(3).strip()
                elif match_cisco:
                    oid, val = match_cisco.group(1), match_cisco.group(3).strip()
                else: continue
                    
                # Normalize OIDs
                if oid.startswith("IF-MIB::ifDescr."):
                    if_index_str = oid.split(".")[-1]
                    oid = f"1.3.6.1.2.1.2.2.1.2.{if_index_str}"
                elif oid.startswith("IF-MIB::ifType."):
                    if_index_str = oid.split(".")[-1]
                    oid = f"1.3.6.1.2.1.2.2.1.3.{if_index_str}"
                elif oid.startswith("iso."):
                    oid = oid.replace("iso.", "1.", 1)
                
                oid = oid.lstrip(".")
                if oid.startswith('1.3.6.1.2.1.2.2.1.2.'):
                    descr_data[oid] = val.strip('"').strip()
                elif oid.startswith('1.3.6.1.2.1.2.2.1.3.'):
                    match_num = re.search(r'(\d+)', val)
                    type_data[oid] = match_num.group(1) if match_num else "0"
    except Exception: return {}

    if not descr_data: return {}

    return DoTheLoop(sys_descr, descr_data, type_data )




def batch_test_files(pattern: str = "snmp*.txt", detailed: bool = False) -> None:
    """Test multiple SNMP output files and provide a summary."""
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No files found matching pattern: {pattern}")
        return
    
    print("=" * 80)
    print(f"SNMP PORT DISCOVERY - BATCH TEST RESULTS")
    print("=" * 80 + "\n")
    
    results = []
    
    for filename in files:
        mapping = test_discover_physical_ports(filename)
        if mapping:
            copper = sum(1 for p in mapping.values() if p["is_copper"])
            sfp = len(mapping) - copper
            results.append({"file": filename, "status": "✓ OK", "ports": len(mapping), "copper": copper, "sfp": sfp, "mapping": mapping})
        else:
            results.append({"file": filename, "status": "✗ FAIL", "ports": 0, "copper": 0, "sfp": 0, "mapping": {}})
    
    print(f"{'File':<35} {'Status':<8} {'Total':<8} {'Copper':<8} {'SFP':<8}")
    print("-" * 80)
    for res in results:
        print(f"{Path(res['file']).name:<35} {res['status']:<8} {res['ports']:<8} {res['copper']:<8} {res['sfp']:<8}")
    
    if detailed:
        print("\n" + "=" * 80 + "\nDETAILED PORT LISTINGS\n" + "=" * 80)
        for res in results:
            if not res["mapping"]: continue
            print(f"\n📁 {res['file']}")
            for lp, info in sorted(res["mapping"].items()):
                ptype = "SFP" if info["is_sfp"] else "Copper"
                print(f"   {lp:2d} | {info['name']:<25} | {ptype:6s} | {info['if_descr']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch test SNMP port discovery")
    parser.add_argument('file', nargs='?', help='Single file to test')
    parser.add_argument('--pattern', default='snmp*.txt', help='Glob pattern for files')
    parser.add_argument('--detailed', '-d', action='store_true', help='Show detailed info')
    
    args = parser.parse_args()
    if args.file:
        m = test_discover_physical_ports(args.file)
        print(json.dumps(m, indent=2))
    else:
        batch_test_files(args.pattern, args.detailed)
