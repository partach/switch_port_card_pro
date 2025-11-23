# Switch port card pro
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-00A1DF?style=flat-square&logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5?style=flat-square)](https://hacs.xyz)
[![HACS Action](https://img.shields.io/github/actions/workflow/status/partach/switch_port_card_pro/validate-hacs.yml?label=HACS%20Action&style=flat-square)](https://github.com/partach/switch_port_card_pro/actions)
[![Installs](https://img.shields.io/github/downloads/partach/switch_port_card_pro/total?color=28A745&label=Installs&style=flat-square)](https://github.com/partach/switch_port_card_pro/releases)
[![License](https://img.shields.io/github/license/partach/switch_port_card_pro?color=ffca28&style=flat-square)](https://github.com/partach/switch_port_card_pro/blob/main/LICENSE)
[![HACS validated](https://img.shields.io/badge/HACS-validated-41BDF5?style=flat-square)](https://github.com/hacs/integration)

This Home Assistant card shows the status of your switch ports and includes SNMP python integration.

<p align="center">
  <img src="https://github.com/partach/hacs_switch_port_card/blob/main/switch-port-card3.png" width="600"/>
  <br>
  <em>Live port status with color coding: 10M/100M (orange), 1G (green), 10G (blue), DOWN (gray)</em>
</p>


First version is veriefied with:
Real-time **28-port status** (24 copper + 4 SFP) for Zyxel XGS1935 (and similar) using **direct entity access**.
But... quite some configurations are possible so will probably work for your switch as well. 

The card is based on and therefor depedent on `SNMP data`. 

**IMPORTANT**: SNMP requires the right baseoid for getting the right data.
This baseoid can be manufacturer dependent. The integration uses baseoids but no garuantee it will always work.

## Features
- Indication of `10M`, `100M`, `1G`, `10G`, `DOWN`
- Optional indication of port name, vlan id, Rx speed, Tx speed
- Cpu load and memory load indication (optional as well)
- Compact mode (for smaller dashboards)
- Hover Tooltip per port showing status details per port
- Card Configuration screen
- Works with defined entities `switch.mainswitch_port_X` + `sensor.mainswitch_port_speed_X` + optional (see below)
- Dark / Light Mode

## Installation
Options:
1. Working on HACS version, coming soon.
2. Already possible to add as HACS--> custom repositories --> repo: partach/switch_port_card_pro, Type:Integration

## Preparing your switch
You need to enable SNMP in your switch. This is different per manufacturer, please follow the switch manual (don't ask me).
What is important that you need:
 * SNMP enabled (duh; although tricky to find on some switches)
 * Define the community string (per default this is named `public` but you can change for slightly better security). Info is needed by integration during setup
 * The example uses SNMP Version v2C that you should set both at switch side and at HA (see below)
 * Set target IP trap desitnation (on your network switch) towards your HA IP
 * Some switches require different additional details settings (follow manufacturer manual)

## Adding one entity to HA
Below you can add directly to your configuration.yaml, 

```yaml
tbd
```

## Coniguration options
The card comes with a configuration dialog that guides the instalation in HA. See below for more details.
```
    tbd.
      name: 'Switch Ports'
      copper_label: 'COPPER'
      sfp_label: 'SFP'
      show_legend: true,
      show_system_info: false  (shows card without cpu, mem, etc.)
      compact_mode: false   (possible to make the card small for tight dashboards)

```

## using the card example
The card has a configuration screen which can be used in stead...
```yaml
  type: custom:switch-port-card
  entity_prefix: mainswitch
  total_ports: 28
  sfp_start_port: 25
  name: Main Switch
  compact_mode: false
  copper_label: GIGABIT
  sfp_label: 10G SFP+
```

## Changelog
See CHANGELOG.md

## Issues
Report at GitHub Issues

## support development
If you want to support this and future developments it would be greatly appreciated

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg?style=flat-square)](https://paypal.me/therealbean)
