# Switch port integration pro
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-00A1DF?style=flat-square&logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5?style=flat-square)](https://hacs.xyz)
[![HACS Action](https://img.shields.io/github/actions/workflow/status/partach/switch_port_card_pro/validate-hacs.yml?label=HACS%20Action&style=flat-square)](https://github.com/partach/switch_port_card_pro/actions)
[![Installs](https://img.shields.io/github/downloads/partach/switch_port_card_pro/total?color=28A745&label=Installs&style=flat-square)](https://github.com/partach/switch_port_card_pro/releases)
[![License](https://img.shields.io/github/license/partach/switch_port_card_pro?color=ffca28&style=flat-square)](https://github.com/partach/switch_port_card_pro/blob/main/LICENSE)
[![HACS validated](https://img.shields.io/badge/HACS-validated-41BDF5?style=flat-square)](https://github.com/hacs/integration)

This Home Assistant integration with card shows the status of your switch ports and includes embedded SNMP integration (no need to setup seperately).

<p align="center">
  <img src="https://github.com/partach/switch_port_card_pro/blob/main/pro%20snmp%20integration%20success.png" width="600"/>
  <br>
  <em>Integration after installation</em>
</p>
<p align="center">
  <img src="https://github.com/partach/switch_port_card_pro/blob/main/pro%20card%20configuration.png" width="600"/>
  <br>
  <em>Live port status with color coding: 10M/100M (orange), 1G (green), 10G (blue), DOWN (gray)</em>
</p>


**IMPORTANT**: SNMP requires the right baseoids for getting the required data.
This baseoid can be manufacturer dependent. The integration uses baseoids that you can configure on the fly and has default some standard ones.

<p align="center">
  <img src="https://github.com/partach/switch_port_card_pro/blob/main/pro%20integration%20setting%20options.png" width="120"/>
  <br>
  <em>integration configuration option after install</em>
</p>

## Features
- No entities have to be set manually for SNMP!
- Indication of `10M`, `100M`, `1G`, '2.5G`, `5G` `10G`, `DOWN`
- Indication of port name, vlan id, Rx speed, Tx speed, POE power, POE budget, POE status 
- Cpu load and memory load indication as well as firmware version
- Compact mode (for smaller dashboards)
- Hover Tooltip per port showing status details per port
- Integration (and card) configuration screen
- Dark / Light Mode

## Installation
Options:
1. Working on HACS version, coming soon.
2. Already possible to add as HACS--> custom repositories --> repo: partach/switch_port_card_pro, Type:Integration (card to be installed seperatly for now)

## Preparing your switch
You need to enable SNMP in your switch. This is different per manufacturer, please follow the switch manual (don't ask me).
What is important that you need:
 * SNMP otion enabled (duh; although tricky to find on some switches)
 * Define the community string (per default this is named `public` but you can change for slightly better security). Info is needed by integration during setup
 * The example uses SNMP Version v2C that you should set both at switch side and at HA (see below)
 * Set target IP trap desitnation (on your network switch) towards your HA IP
 * Some switches require different additional details settings (follow manufacturer manual)

## Coniguration options
The card comes with a configuration dialog that guides the instalation in HA.


## using the card example
The card has a configuration screen which can be used in stead...
```yaml
  type: custom:switch-port-card-pro
  device: xxx
```

## Changelog
See CHANGELOG.md

## Issues
Report at GitHub Issues

## support development
If you want to support this and future developments it would be greatly appreciated

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg?style=flat-square)](https://paypal.me/therealbean)
