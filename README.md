# Switch port integration pro
[![Home Assistant](https://img.shields.io/badge/Home_Assistant-00A1DF?style=flat-square&logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5?style=flat-square)](https://hacs.xyz)
[![HACS Action](https://img.shields.io/github/actions/workflow/status/partach/switch_port_card_pro/validate-hacs.yml?label=HACS%20Action&style=flat-square)](https://github.com/partach/switch_port_card_pro/actions)
[![Installs](https://img.shields.io/github/downloads/partach/switch_port_card_pro/total?color=28A745&label=Installs&style=flat-square)](https://github.com/partach/switch_port_card_pro/releases)
[![License](https://img.shields.io/github/license/partach/switch_port_card_pro?color=ffca28&style=flat-square)](https://github.com/partach/switch_port_card_pro/blob/main/LICENSE)
[![HACS validated](https://img.shields.io/badge/HACS-validated-41BDF5?style=flat-square)](https://github.com/hacs/integration)

This Home Assistant integration (with card included) shows the status of your switch ports and includes embedded SNMP integration (no need to setup SNMP seperately via configuration files).

<p align="center">
  <img src="https://github.com/partach/switch_port_card_pro/blob/main/pro%20snmp%20integration%20success.png" width="600"/>
  <br>
  <em>Integration after installation</em>
</p>
<p align="center">
  <img src="https://github.com/partach/switch_port_card_pro/blob/main/pro%20card%20visual.png" width="600"/>
  <br>
  <em>Live port status with color coding: 10M/100M (orange), 1G (green), 10G (blue), DOWN (gray)</em>
</p>


**IMPORTANT**: SNMP requires the right base-oid's for getting the required data.
This base oid can be manufacturer dependent and are sometimes hard to find. 
The integration uses baseoids that you can configure on the fly and has default some standard ones.

<p align="center">
  <img src="https://github.com/partach/switch_port_card_pro/blob/main/pro%20integration%20setting%20options.png" width="120"/>
  <br>
  <em>integration configuration option after install</em>
</p>

## Features
- No entities have to be set manually for SNMP!
- Supports multiple hubs (switch instances). You can monitor your whole switch farm from one dashboard
- Indication of `10M`, `100M`, `1G`, `2.5G`, `5G` `10G`, `DOWN`
- Fully configurable UI to show the information per port as you want it.
- Automatic detection of number of available ports (if standard oid is honored by network Switch)
- Visible vlan tagging (ports show to which VLAN they belong)
- Indication of port name, vlan id, Rx speed, Tx speed, POE power, POE status,  
- Cpu load and memory load indication as well as firmware version.
- Custom system OID possibility (monitor your specific need like temperature)
- Custom per port OID (will be 'walked' and information collected per port)
- Compact mode (for smaller dashboards)
- Hover Tooltip per port showing status details per port
- Integration (and card) configuration screen
- Dark / Light Mode

## Installation
Options:
1. Install via HACS  [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=partach&repository=switch_port_card_pro&category=plugin) after HA reboot; 'add integration' and choose switch_port_card_pro in the list
2. Manually via HACS--> custom repositories --> repo: partach/switch_port_card_pro, Type:Integration
   * Card to be installed seperatly for now. It is in the reposity under www/community/
   * Install card under /www/community/switch_port_card_pro/switch_port_card_pro.js
   * To add lovelace card: Go to System -> Dashboards -> Resources and fill in URL: /local/switch_port_card_pro/switch_port_card_pro.js Type:java script
   * reboot, chose 'add integration' and select switch_port_card_pro in the list
   * Let the install config guide you as it asks you network switch IP and SNMP community string (make sure network switch is configured for SNMP)

## Preparing your network switch
You need to enable SNMP in your switch. This is different per manufacturer, please follow the switch manual.
What is important that you need:
 * SNMP option enabled (tricky to find on some switches)
 * Define the community string (per default this is named `public` but you can change for slightly better security). Info is needed by integration during setup
 * The example uses SNMP Version v2C that you should set both at switch side and during initial integration configuration
 * Set target IP trap desitnation (on your network switch) towards your HA IP
 * Some switches require different additional details settings (follow manufacturer manual)

## Coniguration options
The card comes with a configuration dialog that guides the instalation in HA.
<p align="center">
  <img src="https://github.com/partach/switch_port_card_pro/blob/main/pro%20card%20configuration.png" width="600"/>
  <br>
  <em>configuration of the card</em>
</p>

## using the card example
The card has a configuration screen which can be used in stead...
```yaml
  type: custom:switch-port-card-pro
  device: sensor.switch_192_168_1_1
  name: XGS1935
  compact_mode: false
  show_total_bandwidth: false
  show_live_traffic: true
  total_ports: 28
  sfp_start_port: 25
  show_system_info: true
  show_port_type_labels: false
  custom_text: Temperature MAC
```

## verified oids for zyxel 1935
Example uses switch name 'switch 192.168.1.1'.

For the 'port oid's' the integration will walk these oid's (meaning the sw puts .1 for port 1 behind it, etc.)
| Port # | Entity ID Example                          | Attribute        | Description                          | SNMP OID (or note)                  |
|-------|---------------------------------------------|------------------------|--------------------------------------|-------------------------------------|
| –     | `sensor.switch_192_168_1_1_total_bandwidth` | `state`                | Total switch bandwidth (Mbps)        | Custom aggregate (SW calculates)     |
| –     | `sensor.switch_192_168_1_1_system_cpu`      | `state`                | CPU usage (%)                        | `1.3.6.1.4.1.890.1.15.3.2.4.0`  |
| –     | `sensor.switch_192_168_1_1_system_memory`   | `state`                | Memory usage (%)                     | `1.3.6.1.4.1.890.1.15.3.2.5.0`  |
| –     | `sensor.switch_192_168_1_1_firmware`     | `state`                | Firmware text                     | `1.3.6.1.4.1.890.1.15.3.1.6.0`  |
| –     | `sensor.switch_192_168_1_1_hostname`     | `state`                | The vendor name and type                     | `1.3.6.1.2.1.1.5.0`  |
| –     | `sensor.switch_192_168_1_1_uptime`     | `state`                | The up time of the switch                     | `1.3.6.1.2.1.1.3.0`  |
| x     | `sensor.switch_192_168_1_1_port_x_status`   | `port_name`            | Port description / name              | `1.3.6.1.2.1.31.1.1.1.18`        |
| x     | `sensor.switch_192_168_1_1_port_x_status`   | `status`               | Link state (up/down)                 | `1.3.6.1.2.1.2.2.1.8`             |
| x     | `sensor.switch_192_168_1_1_port_x_status`   | `speed_bps`            | Current link speed in bps            | `1.3.6.1.2.1.2.2.1.5`         |
| x     | `sensor.switch_192_168_1_1_port_x_status`   | `rx_bps_live`          | Real-time RX bandwidth (bps)         | Custom calculation / script         |
| x     | `sensor.switch_192_168_1_1_port_x_status`   | `tx_bps_live`          | Real-time TX bandwidth (bps)         | Custom calculation / script         |
| x     | `sensor.switch_192_168_1_1_port_x_status`   | `poe_enabled`          | PoE enabled on port                  | `1.3.6.1.4.1.<vendor>.poe.x`       |
| x     | `sensor.switch_192_168_1_1_port_x_status`   | `vlan_id`              | Current VLAN (if supported)          | `1.3.6.1.2.1.17.7.1.4.5.1.1`     |


## Changelog
See CHANGELOG.md

## Issues
Report at GitHub Issues

## support development
If you want to support this and future developments it would be greatly appreciated

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg?style=flat-square)](https://paypal.me/therealbean)
