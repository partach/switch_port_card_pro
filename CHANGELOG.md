## Changelog
### [0.9.0] - Major update
- Refactoring, faster startup on HA restart.
- Async snmp engine creation (does not solve HA warning, needs pysnmp 7.1 update)
- Card is now part of integration (but requires 1 manual step to add resource, see readme)
- Card is now visible in HA Card picker!
- Small card updates (improve hoover with click, tigther grouping of ports, background option)
- Resolved issues #8, #13, #14
### Breaking
- could break existing hubs (if so delete hub, re-add and re-configure)
- the separate repository with only the pro card is obsolete, please remove first
  
### [0.8.3-pre] - Refactoring
- Cisco auto port detection fix
- card + integration in one repo
  
### [0.8.2] - Update on auto port detection mode
- Netgear 724T auto detect and unifi fixed 

### [0.8.1] - Card installed separately via HACS
- Improved auto port detection for unifi after example from users
- card install via hacs in progress. Already available via custom repositories (partach/switch-port-card-pro-card)

### [0.8.0] - Port color modes
- Added port color modes (Traffic heatmap, Link speed, Actual speed classification, Vlan)
- only card is updated
  
### [0.7.2] - Live on HACS
- available via HACS!
- de and nl language file added
- Updated Readme with HACS link
  
### [0.7.0] - Hacs compliant
- Brands compliance now done.
- Making port visuals in card configurable for end user
- Other smaller optimizations

### [0.6.0] - Added language file
- en.json now added. More will be added later
- Integration Configuration screen much more descriptive
- Small improvement on card visual

### [0.5.5] - Official Release
- Added custom OID (use any oid value you want in your card)
- Configurable name for custom OID in card
- Updated configuration possibilities of integration (and card)
- Configurable update time (20s per default)
  
### [0.5.4] - Extensions
- VLAN indication per port visual in the card
- Fully auto port detection (via SNMP)
- Title enable/disable per port section
- System information show / hide
### Fixed
- 32 bit counter wrap around issue for actual tx/rx speed
- Issue with auto port detection not updating config settings


### [0.5.3] - Improvements
- Not showing POE attributes when not configured (no oids available)
- First rudimentory version of auto (number of) ports detection ('interface'description part of port attribute) 
 
### [0.5.2] - live rx/tx support
- Based on lifetime rx/tx counter determine the current rx/tx speed per port
- Boolean setting in UI to turn on and off the real time rx/tx speeds display
- Updated card configuration with ha look and feel
- Updated device discovery mechanism and functioning 
### Fixed
- Bandwith calculation improvements
- device selection for card
### Documentation
- bringing README up to date

### [0.5.1] - Full Multi-Switch Support
- Fixed unique ID conflicts when using multiple switches
- Added proper device registry separation using entry_id
- Dynamic device naming (hostname → config title → IP)
- Real firmware and model in device info
- 100% future-proof multi-instance support
### Fixed
- Multi instance handling with unique IDs
### Documentation
- bringing README up to date
  
### [0.5.0] – 2025-11-29
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
