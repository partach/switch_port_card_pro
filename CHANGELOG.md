# Changelog
## [0.5.5] - Official Release
- Added custom OID (use any oid value you want in your card)
- Configurable name for custom OID in card
- Updated configuration possibilities of integration (and card)
- Configurable update time (20s per default)
  
## [0.5.4] - Extensions
- VLAN indication per port visual in the card
- Fully auto port detection (via SNMP)
- Title enable/disable per port section
- System information show / hide
### Fixed
- 32 bit counter wrap around issue for actual tx/rx speed
- Issue with auto port detection not updating config settings


## [0.5.3] - Improvements
- Not showing POE attributes when not configured (no oids available)
- First rudimentory version of auto (number of) ports detection ('interface'description part of port attribute) 
 
## [0.5.2] - live rx/tx support
- Based on lifetime rx/tx counter determine the current rx/tx speed per port
- Boolean setting in UI to turn on and off the real time rx/tx speeds display
- Updated card configuration with ha look and feel
- Updated device discovery mechanism and functioning 
### Fixed
- Bandwith calculation improvements
- device selection for card
### Documentation
- bringing README up to date

  ## [0.5.1] - Full Multi-Switch Support
- Fixed unique ID conflicts when using multiple switches
- Added proper device registry separation using entry_id
- Dynamic device naming (hostname → config title → IP)
- Real firmware and model in device info
- 100% future-proof multi-instance support
### Fixed
- Multi instance handling with unique IDs
### Documentation
- bringing README up to date
  
## [0.5.0] – 2025-11-29
### Features
- Almost HACS compliant release (brands only thing still missing)
- Initial functional working release of Switch Port Card Pro integration for Home Assistant.
- Full SNMP monitoring for switch ports, including status, speed, vlan, total bandwidth, POE and more.
- System sensors for CPU, memory, uptime, firmware and hostname.
- Configurable OIDs and port range via options flow.
- Support any SNMP-enabled switches.
- Companion Lovelace card for visual port status, cpu, mem and more. (needs to be released seperately)
### Fixed
- PYSNMP 7.1 compliant
- Hacssfest compliancy and validation rules
### Documentation
- bringing README up to date
