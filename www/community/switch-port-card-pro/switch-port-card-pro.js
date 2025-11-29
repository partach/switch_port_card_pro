// switch-port-card-pro.js
// v1.0.0 � The One That Works. Forever.

class SwitchPortCardPro extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  static getConfigElement() {
    return document.createElement("switch-port-card-pro-editor");
  }

  static getStubConfig() {
    return {
      type: "custom:switch-port-card-pro",
      name: "Network Switch",
      device: "",
      entity: "sensor.mainswitch_total_bandwidth_mbps",
      total_ports: 28,
      sfp_start_port: 25,
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      compact_mode: false,
    };
  }

  setConfig(config) {
    this._config = {
      name: "Network Switch",
      total_ports: 28,
      sfp_start_port: 25,
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      compact_mode: false,
      ...config  // overwrite with user values
    };
  }

  set hass(hass) {
    this._hass = hass;
    
    // Initialize config with defaults if not set yet
    if (!this._config) {
      this._config = {
        name: "Network Switch",
        total_ports: 28,
        sfp_start_port: 25,
        show_total_bandwidth: true,
        max_bandwidth_gbps: 100,
        compact_mode: false
      };
    }
    
    if (!this._entities || this._lastHass !== hass) {
      this._entities = this._collectEntities(hass);
      this._lastHass = hass;
    }
    if (!this._root) this._createSkeleton();
    this._render();
  }

  _collectEntities(hass) {
    const entities = {};
    if (!this._config || (!this._config.device && !this._config.entity)) return entities;

    let deviceId = this._config.device;
    let entityPrefix = null;
    let deviceEntities = [];

    // If device is selected, get entities from device registry
    if (deviceId && hass.devices) {
      const device = Object.values(hass.devices).find(d => d.id === deviceId);
      if (device) {
        // Get all entity_ids linked to this device
        deviceEntities = Object.values(hass.entities)
          .filter(e => e.device_id === deviceId)
          .map(e => e.entity_id);
        console.log("Found device entities:", deviceEntities);
      }
    }

    // Fallback to entity prefix if no device found
    if (deviceEntities.length === 0 && this._config.entity) {
      const ent = hass.states[this._config.entity];
      if (ent?.attributes?.device_id) {
        deviceId = ent.attributes.device_id;
      } else {
        // Extract prefix from entity name
        const parts = this._config.entity.split("_total_bandwidth");
        if (parts.length > 0) {
          entityPrefix = parts[0] + "_";
        }
      }
    }

    console.log("Collecting entities - Device ID:", deviceId, "Prefix:", entityPrefix);

    // Search using device_id attribute (original method)
    if (deviceId && deviceEntities.length === 0) {
      Object.values(hass.states).forEach(entity => {
        if (entity.attributes?.device_id !== deviceId) return;
        deviceEntities.push(entity.entity_id);
      });
    }

    // Match entities
    const entitiesToSearch = deviceEntities.length > 0 ? deviceEntities : Object.keys(hass.states);
    
    entitiesToSearch.forEach(entityId => {
      if (typeof entityId !== 'string') entityId = entityId;
      
      // If using prefix, filter first
      if (entityPrefix && !entityId.startsWith(entityPrefix)) return;

      const id = entityId;
      const entity = hass.states[entityId];
      
      if (!entity) return;

      if (id.includes("_total_bandwidth")) entities.bandwidth = entity;
      else if (id.includes("_system_cpu") || id.includes("cpu_usage")) entities.cpu = entity;
      else if (id.includes("_system_memory") || id.includes("memory_usage")) entities.memory = entity;
      else if (id.includes("_system_uptime") || id.includes("uptime")) entities.uptime = entity;
      else if (id.includes("_system_hostname") || id.includes("hostname")) entities.hostname = entity;
      else if (id.includes("_total_poe") || id.includes("total_poe")) entities.total_poe = entity;
      else if (id.includes("_firmware") || id.includes("firmware")) entities.firmware = entity;
      else if (id.includes("_port_") && id.includes("_status")) {
        const match = id.match(/_port_(\d+)_status/);
        if (match) entities[`port_${match[1]}_status`] = entity;
      }
    });

    console.log("Collected entities:", Object.keys(entities));
    return entities;
  }

  _createSkeleton() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          color: var(--primary-text-color);
          padding: 16px;
          border-radius: var(--ha-card-border-radius, 12px);
          font-family: var(--ha-font-family, Roboto);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
          font-size: 1.2em;
          font-weight: 600;
        }
        .system-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
          gap: 12px;
          margin: 16px 0;
        }
        .info-box {
          background: var(--primary-background-color, #f0f0f0);
          padding: 4px;
          border-radius: 10px;
          text-align: center;
          border: 1px solid var(--divider-color);
        }
        .info-value { font-size: 1.2em; font-weight: bold; }
        .info-label { font-size: 0.8em; opacity: 0.8; color: var(--secondary-text-color); }

        .gauge {
          height: 18px;
          background: var(--light-primary-color);
          border-radius: 12px;
          overflow: hidden;
          margin: 16px 0;
          display: none;
          position: relative;
        }
        .gauge-fill {
          height: 100%;
          background: linear-gradient(90deg,
            var(--label-badge-green, #4caf50),
            var(--label-badge-yellow, #ff9800) 50%,
            var(--label-badge-red, #f44336)
          );
          background-size: 300% 100%;
          width: 100%;
          transition: background-position 0.8s ease;
        }

        .ports-section { margin-top: 10px; }
        .section-label {
          font-size: 0.9em;
          justify-content: center;
          font-weight: 600;
          color: var(--secondary-text-color);
          margin: 16px 0 8px;
        }
        .ports-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(50px, 1fr));
          gap: 6px;
        }
        .port {
          aspect-ratio: 2.2 / 1;
          background: var(--light-primary-color);
          border-radius: 8px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          font-weight: bold;
          font-size: 0.8em;
          cursor: default;
          transition: all 0.2s ease;
          position: relative;
          border: 1px solid var(--divider-color);
        }
        .port:hover { transform: scale(1.08); z-index: 10; }
        .port-num { font-size: 0.9em; }
        .port-status { font-size: 0.7em; margin-top: 2px; }
        .port.off { background: var(--disabled-background-color); opacity: 0.7; color: var(--secondary-text-color); }
        .port.on-10g  { background: #1e88e5; color: white; }
        .port.on-5g   { background: #1565c0; color: white; }
        .port.on-2_5g { background: #1976d2; color: white; }
        .port.on-1g   { background: #4caf50; color: white; }
        .port.on-100m { background: #ff9800; color: black; }
        .port.on-10m  { background: #f44336; color: white; }
        .port.sfp { border: 2px solid #2196f3; box-shadow: 0 0 10px rgba(33,150,243,0.4); }
        .poe-indicator {
          position: absolute;
          top: 2px;
          right: 4px;
          font-size: 0.7em;
          font-weight: bold;
          color: #00ff00;
          text-shadow: 0 0 4px #000;
        }
        .compact .ports-grid { grid-template-columns: repeat(auto-fit, minmax(40px, 1fr)); }
        .compact .port { font-size: 0.6em; }
        @media (max-width: 600px) {
          .ports-grid { grid-template-columns: repeat(auto-fit, minmax(40px, 1fr)); }
        }
      </style>

      <ha-card>
        <div class="header">
          <span id="title">Switch</span>
          <span id="bandwidth"> Mbps</span>
        </div>
        <div class="system-grid" id="system"></div>
        <div class="gauge" id="gauge"><div class="gauge-fill" id="fill"></div></div>
        <div class="ports-section ${this._config.compact_mode ? 'compact' : ''}">
          <div class="section-label">COPPER PORTS</div>
          <div class="ports-grid" id="copper"></div>
          <div class="section-label">SFP/FIBER PORTS</div>
          <div class="ports-grid" id="sfp"></div>
        </div>
      </ha-card>
    `;
    this._root = this.shadowRoot.querySelector(".header");
  }

  _formatTime(seconds) {
    if (!seconds) return "�";
    const h = Math.floor(seconds / 3600);
    const d = Math.floor(h / 24);
    if (d > 0) return `${d}d ${h % 24}h`;
    if (h > 0) return `${h}h ${Math.floor((seconds % 3600) / 60)}m`;
    return `${Math.floor(seconds / 60)}m`;
  }

  _render() {
    // Create skeleton first if it doesn't exist
    if (!this._root) this._createSkeleton();

    if (!this._hass || !this._config) {
      const header = this.shadowRoot.querySelector(".header");
      if (header) {
        header.innerHTML = `<span style="color:var(--label-badge-orange)">Loading card...</span>`;
      }
      return;
    }
    
    if (Object.keys(this._entities || {}).length === 0) {
      const header = this.shadowRoot.querySelector(".header");
      if (header) {
        header.innerHTML = `<span style="color:var(--label-badge-red)">Data not loaded yet check integration</span>`;
      }
      return;
    }

    const bw = this._entities.bandwidth;
    const cpu = this._entities.cpu;
    const mem = this._entities.memory;
    const firmware = this._entities.firmware;
    const uptime = this._entities.uptime;
    const host = this._entities.hostname;
    const poeTotal = this._entities.total_poe;

    // Header
    const hostname = host?.state?.trim() || null;
    this.shadowRoot.getElementById("title").textContent = this._config.name || hostname || "Switch";
    this.shadowRoot.getElementById("bandwidth").textContent = bw ? `${Number(bw.state/8000).toFixed(1)} MB/s` : " MB/s";

    // System info
    this.shadowRoot.getElementById("system").innerHTML = `
      ${cpu?.state ? `<div class="info-box"><div class="info-value">${Math.round(cpu.state)}%</div><div class="info-label">CPU</div></div>` : ''}
      ${mem?.state ? `<div class="info-box"><div class="info-value">${Math.round(mem.state)}%</div><div class="info-label">Memory</div></div>` : ''}
      ${uptime?.state ? `<div class="info-box"><div class="info-value">${this._formatTime(Number(uptime.state))}</div><div class="info-label">Uptime</div></div>` : ''}
      ${host?.state ? `<div class="info-box"><div class="info-value">${host.state}</div><div class="info-label">Host</div></div>` : ''}
      ${poeTotal?.state ? `<div class="info-box"><div class="info-value">${poeTotal.state} W</div><div class="info-label">PoE Total</div></div>` : ''}
      ${firmware?.state ? `<div class="info-box"><div class="info-value;font-size:5px">${firmware.state}</div><div class="info-label">Firmware</div></div>` : ''}
    `;

    // Gauge
    const gauge = this.shadowRoot.getElementById("gauge");
    const fill = this.shadowRoot.getElementById("fill");
    if (this._config.show_total_bandwidth !== false && bw?.state) {
      gauge.style.display = "block";
      const max = (this._config.max_bandwidth_gbps || 100) * 1000;
      const pct = Math.min((bw.state / max) * 100, 100);
      fill.style.backgroundPosition = `${100 - pct}% 0`;
    } else {
      gauge.style.display = "none";
    }

    // Ports
    const total = this._config.total_ports || 28;
    const sfpStart = this._config.sfp_start_port || 25;
    const copper = this.shadowRoot.getElementById("copper");
    const sfp = this.shadowRoot.getElementById("sfp");
    copper.innerHTML = "";
    sfp.innerHTML = "";

    for (let i = 1; i <= total; i++) {
      const ent = this._entities[`port_${i}_status`];
      const state = ent?.state || "off";
      const isOn = state === "on";

      const speedMbps = parseInt(ent?.attributes?.speed_bps / 1e6 || "0") || parseInt(ent?.attributes?.speed || "0");
      const rxBps = parseInt(ent?.attributes?.rx_bps || "0");
      const txBps = parseInt(ent?.attributes?.tx_bps || "0");
      const name = (ent?.attributes?.port_name?.trim() || `Port ${i}`);
      const vlan = ent?.attributes?.vlan_id;
      const poeEnabled = ent?.attributes?.poe_enabled === true;

      let speedClass = "off";
      let speedText = "OFF";
      let direction = "";

      if (isOn && speedMbps > 0) {
        if (speedMbps >= 10000) { speedClass = "on-10g";  speedText = "10G"; }
        else if (speedMbps >= 5000)  { speedClass = "on-5g";   speedText = "5G"; }
        else if (speedMbps >= 2500)  { speedClass = "on-2_5g"; speedText = "2.5G"; }
        else if (speedMbps >= 1000)  { speedClass = "on-1g";   speedText = "1G"; }
        else if (speedMbps >= 100)   { speedClass = "on-100m"; speedText = "100M"; }
        else if (speedMbps >= 10)    { speedClass = "on-10m";  speedText = "10M"; }
        else { speedText = `${speedMbps}M`; }

        if (rxBps > txBps * 1.8) direction = "Down";
        else if (txBps > rxBps * 1.8) direction = "Up";
      }

      const div = document.createElement("div");
      div.className = `port ${speedClass} ${i >= sfpStart ? "sfp" : ""}`;
      div.title = `${name}\nState: ${isOn ? "UP" : "DOWN"}\nSpeed: ${speedText}${vlan ? `\nVLAN: ${vlan}` : ""}\nRX: ${(rxBps/1e6).toFixed(2)} Mb/s\nTX: ${(txBps/1e6).toFixed(2)} Mb/s`;

      div.innerHTML = `
        <div class="port-num">${i}</div>
        <div class="port-status">${direction} ${speedText}</div>
        ${poeEnabled ? '<div class="poe-indicator">P</div>' : ''}
      `;

      (i < sfpStart ? copper : sfp).appendChild(div);
    }
  }

  getCardSize() {
    return this._config.compact_mode ? 5 : 8;
  }
}

// Editor
class SwitchPortCardProEditor extends HTMLElement {
  setConfig(config) {
    this._config = config || {
      name: "Network Switch",
      total_ports: 28,
      sfp_start_port: 25,
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      compact_mode: false
    };
  }

  getConfig() {
    return this._config;
  }

  set hass(hass) {
    this._hass = hass;
    if (!hass) return;
    
    // Re-render if config changed
    if (this._lastConfig === JSON.stringify(this._config)) return;
    this._lastConfig = JSON.stringify(this._config);
    
    // Ensure _config exists
    if (!this._config) {
      this._config = {
        name: "Network Switch",
        total_ports: 28,
        sfp_start_port: 25,
        show_total_bandwidth: true,
        max_bandwidth_gbps: 100,
        compact_mode: false
      };
    }

    // Get devices from hass.states that have device_id
    const deviceMap = {};
    Object.values(hass.states).forEach(entity => {
      const devId = entity.attributes?.device_id;
      if (devId) {
        if (!deviceMap[devId]) {
          deviceMap[devId] = {
            id: devId,
            name: entity.attributes?.device_name || devId
          };
        }
      }
    });

    const devices = Object.values(deviceMap).sort((a, b) => a.name.localeCompare(b.name));

    const entities = Object.keys(hass.states)
      .filter(e => e.includes("switch_port_card_pro") || e.includes("_port_") || e.includes("_bandwidth"))
      .sort();

    this.innerHTML = `
      <style>
        .row { margin: 12px 0; display: flex; align-items: center; gap: 12px; }
        label { min-width: 160px; font-weight: 500; }
        select, input { flex: 1; padding: 8px; border-radius: 6px; border: 1px solid #666; background: #333; color: white; }
        .checkbox { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
        .help { font-size: 0.8em; color: #aaa; margin-top: 4px; }
      </style>
      <div style="padding: 16px;">
        <div class="row">
          <label>Title</label>
          <input type="text" data-key="name" value="${this._config.name || ''}">
        </div>

        <div class="row">
          <label>Device (Recommended)</label>
          <select data-key="device">
            <option value="">-- Select your switch --</option>
            ${devices.map(d => `
              <option value="${d.id}" ${d.id === this._config.device ? 'selected' : ''}>
                ${d.name}
              </option>
            `).join('')}
          </select>
        </div>

        <div class="row">
          <label>Fallback Entity</label>
          <select data-key="entity">
            <option value="">-- Optional --</option>
            ${entities.map(e => `
              <option value="${e}" ${e === this._config.entity ? 'selected' : ''}>
                ${hass.states[e]?.attributes?.friendly_name || e}
              </option>
            `).join('')}
          </select>
        </div>

        <div class="row"><label>Total Ports</label><input type="number" data-key="total_ports" value="${this._config.total_ports || 28}"></div>
        <div class="row"><label>First SFP Port</label><input type="number" data-key="sfp_start_port" value="${this._config.sfp_start_port || 25}"></div>

        <div class="checkbox">
          <input type="checkbox" data-key="show_total_bandwidth" ${this._config.show_total_bandwidth !== false ? 'checked' : ''}>
          <label>Show Bandwidth Gauge</label>
        </div>
        <div class="row" style="display:${this._config.show_total_bandwidth !== false ? 'flex' : 'none'};">
          <label>Max Bandwidth (Gbps)</label>
          <input type="number" step="10" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps || 100}">
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="compact_mode" ${this._config.compact_mode ? 'checked' : ''}>
          <label>Compact Mode</label>
        </div>
      </div>
    `;

    this.querySelectorAll("[data-key]").forEach(el => {
      el.addEventListener("change", (e) => {
        const key = el.dataset.key;
        let value = el.type === "checkbox" ? el.checked : el.value;
        if (el.type === "number") value = parseInt(value) || 0;

        this._config = { ...this._config, [key]: value };
        if (key === "show_total_bandwidth") {
          this.querySelectorAll(".row")[5].style.display = value ? "flex" : "none";
        }
        this.dispatchEvent(new CustomEvent("config-changed", {
          detail: { config: this._config },
          bubbles: true,
          composed: true
        }));
      });
    });
  }
}

customElements.define("switch-port-card-pro", SwitchPortCardPro);
customElements.define("switch-port-card-pro-editor", SwitchPortCardProEditor);
