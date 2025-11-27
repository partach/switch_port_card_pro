// switch-port-card-dev.js
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
    if (!config.device && !config.entity) {
      throw new Error("Please specify 'device' or 'entity'");
    }
    this._config = { ...config };
  }

  set hass(hass) {
    this._hass = hass;
    // Recalculate entities only if needed, to avoid constant re-rendering
    if (!this._entities || this._lastHassUpdate !== hass) {
      this._entities = this._collectEntities();
      this._lastHassUpdate = hass;
    }
    if (!this._root) this._createSkeleton();
    this._render();
  }

  _collectEntities() {
    const entities = {};

    // Determine the device ID from the config, prioritizing 'device' ID
    let deviceId = this._config.device;
    if (!deviceId && this._config.entity) {
      const mainEntity = this._hass.states[this._config.entity];
      if (mainEntity?.attributes?.device_id) {
        deviceId = mainEntity.attributes.device_id;
      }
    }

    if (deviceId) {
      // Collect all entities belonging to the device
      Object.values(this._hass.states).forEach(entity => {
        if (entity.attributes?.device_id === deviceId) {
          // Standardize names for easy lookup
          const id = entity.entity_id;
          if (id.includes("_total_bandwidth_mbps")) {
            entities["bandwidth"] = entity;
          } else if (id.includes("_system_cpu")) {
            entities["cpu"] = entity;
          } else if (id.includes("_system_memory")) {
            entities["memory"] = entity;
          } else if (id.includes("_system_uptime")) {
            entities["uptime"] = entity;
          } else if (id.includes("_system_hostname")) {
            entities["hostname"] = entity;
          } else if (id.includes("_port_") && id.includes("_status")) {
            // Port Status entity (holds all port data in attributes)
            const match = id.match(/_port_(\d+)_status/);
            if (match) {
              entities[`port_${match[1]}_status`] = entity;
            }
          }
        }
      });
    }

    return entities;
  }

  _createSkeleton() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          /* Use HA variables for standard look and feel */
          background: var(--ha-card-background, var(--card-background-color, #fff)); 
          color: var(--primary-text-color, #000);
          padding: 16px;
          border-radius: var(--ha-card-border-radius, 12px);
          font-family: var(--ha-font-family, Roboto);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          font-size: 1.5em;
          font-weight: 600;
          color: var(--ha-card-header-color, var(--primary-text-color));
        }
        .system-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
          gap: 12px;
          margin: 16px 0;
        }
        .info-box {
          background: var(--primary-background-color);
          padding: 10px;
          border-radius: 10px;
          text-align: center;
          border: 1px solid var(--divider-color);
        }
        .info-value { font-size: 1.4em; font-weight: bold; }
        .info-label { font-size: 0.8em; opacity: 0.8; }
        .gauge {
          height: 24px;
          background: var(--light-primary-color);
          border-radius: 12px;
          overflow: hidden;
          margin: 16px 0;
          display: none;
        }
        .gauge-fill {
          height: 100%;
          /* Gradient for visual feedback (Green -> Yellow -> Red) */
          background: linear-gradient(90deg, var(--label-badge-green, #4caf50), var(--label-badge-yellow, #ff9800), var(--label-badge-red, #f44336));
          width: 0%;
          transition: width 0.8s ease;
        }
        .ports-section { margin-top: 20px; }
        .section-label {
          font-size: 0.9em;
          font-weight: 600;
          color: var(--secondary-text-color);
          margin: 16px 0 8px;
        }
        .ports-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(50px, 1fr)); /* Use auto-fit for better responsiveness */
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
          font-size: 0.75em;
          cursor: default;
          transition: all 0.2s ease;
          position: relative;
          border: 1px solid var(--divider-color);
        }
        .port:hover { transform: scale(1.08); z-index: 10; }
        .port-num { font-size: 0.9em; }
        .port-status { font-size: 0.7em; margin-top: 2px; }

        /* Speed classes - Using HA colors for consistency */
        .port.on-10g   { background: var(--label-badge-blue); color: white; }
        .port.on-5g    { background: var(--label-badge-blue-darker, #0d47a1); color: white; }
        .port.on-2_5g  { background: var(--label-badge-blue-dark, #1565c0); color: white; }
        .port.on-1g    { background: var(--label-badge-green); color: white; }
        .port.on-100m  { background: var(--label-badge-yellow); color: black; }
        .port.on-10m   { background: var(--label-badge-orange); color: white; }
        .port.off      { background: var(--disabled-background-color); color: var(--secondary-text-color); opacity: 0.7; }
        .port.sfp      { border: 2px solid var(--label-badge-blue); box-shadow: 0 0 8px rgba(33, 150, 243, 0.3); }

        .compact .ports-grid { grid-template-columns: repeat(auto-fit, minmax(40px, 1fr)); }
        .compact .port { font-size: 0.6em; }

        @media (max-width: 600px) {
          .ports-grid { grid-template-columns: repeat(auto-fit, minmax(40px, 1fr)); }
        }
      </style>

      <ha-card>
        <div class="header">
          <span id="title">Switch</span>
          <span id="bandwidth">— Mbps</span>
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
    this._root = true;
  }

  _formatTime(seconds) {
    if (!seconds) return '—';
    const h = Math.floor(seconds / 3600);
    const d = Math.floor(h / 24);
    if (d > 0) return `${d}d ${h % 24}h`;
    if (h > 0) return `${h}h ${Math.floor((seconds % 3600) / 60)}m`;
    return `${Math.floor(seconds / 60)}m`;
  }

  _render() {
    if (Object.keys(this._entities).length === 0) {
      this.shadowRoot.querySelector(".header").innerHTML = 
        `<span style="color:var(--label-badge-red)">No device/entities found or data yet</span>`;
      return;
    }

    const bw = this._entities.bandwidth;
    const cpu = this._entities.cpu;
    const mem = this._entities.memory;
    const uptime = this._entities.uptime;
    const host = this._entities.hostname;

    // Header
    this.shadowRoot.getElementById("title").textContent = 
      this._config.name || host?.state || "Switch";
    this.shadowRoot.getElementById("bandwidth").textContent = 
      bw ? `${Number(bw.state).toFixed(1)} Mbps` : "— Mbps";

    // System info
    const sys = this.shadowRoot.getElementById("system");
    sys.innerHTML = `
      ${cpu?.state ? `<div class="info-box"><div class="info-value">${Math.round(cpu.state)}%</div><div class="info-label">CPU</div></div>` : ''}
      ${mem?.state ? `<div class="info-box"><div class="info-value">${Math.round(mem.state)}%</div><div class="info-label">Memory</div></div>` : ''}
      ${uptime?.state ? `<div class="info-box"><div class="info-value">${this._formatTime(Number(uptime.state))}</div><div class="info-label">Uptime</div></div>` : ''}
      ${host?.state ? `<div class="info-box"><div class="info-value">${host.state}</div><div class="info-label">Host</div></div>` : ''}
    `;

    // Gauge
    const gauge = this.shadowRoot.getElementById("gauge");
    const fill = this.shadowRoot.getElementById("fill");
    if (this._config.show_total_bandwidth !== false && bw?.state) {
      gauge.style.display = "block";
      const max = (this._config.max_bandwidth_gbps || 100) * 1000;
      const pct = Math.min((bw.state / max) * 100, 100);
      fill.style.width = pct + "%";
      // Set gauge color based on percentage (simple traffic light)
      if (pct < 33) fill.style.backgroundColor = "var(--label-badge-green)";
      else if (pct < 66) fill.style.backgroundColor = "var(--label-badge-yellow)";
      else fill.style.backgroundColor = "var(--label-badge-red)";
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
      const portEnt = this._entities[`port_${i}_status`];
      
      const state = portEnt?.state || "off";
      const isOn = state === "on";
      // Data is now pulled from attributes of the PortStatusSensor
      const speedBps = parseInt(portEnt?.attributes?.speed_bps || "0");
      const rxBps = parseInt(portEnt?.attributes?.rx_bps || "0");
      const txBps = parseInt(portEnt?.attributes?.tx_bps || "0");
      const portName = portEnt?.attributes?.port_name || `Port ${i}`;
      const vlanId = portEnt?.attributes?.vlan_id;

      let speedClass = "off";
      let speedText = "";
      if (isOn) {
        if (speedBps >= 10000000000) { speedClass = "on-10g"; speedText = "10G"; }
        else if (speedBps >= 5000000000) { speedClass = "on-5g"; speedText = "5G"; }
        else if (speedBps >= 2500000000) { speedClass = "on-2_5g"; speedText = "2.5G"; }
        else if (speedBps >= 1000000000) { speedClass = "on-1g"; speedText = "1G"; }
        else if (speedBps >= 100000000) { speedClass = "on-100m"; speedText = "100M"; }
        else if (speedBps >= 10000000) { speedClass = "on-10m"; speedText = "10M"; }
        else { speedClass = "on-1g"; speedText = "UNK"; } // fallback if connected but no speed
      } else {
        speedText = "OFF";
      }

      const div = document.createElement("div");
      div.className = `port ${speedClass} ${i >= sfpStart ? "sfp" : ""}`;
      
      let tooltip = `${portName}\nState: ${isOn ? 'UP' : 'DOWN'}\nSpeed: ${speedText}`;
      if (vlanId !== undefined) {
        tooltip += `\nVLAN: ${vlanId}`;
      }
      // Show raw traffic in the tooltip (Mb/s)
      tooltip += `\nRX: ${(rxBps / 1000000).toFixed(2)} Mb/s\nTX: ${(txBps / 1000000).toFixed(2)} Mb/s`;
      div.title = tooltip;
      
      div.innerHTML = `
        <div class="port-num">${i}</div>
        <div class="port-status">${speedText}</div>
      `;
      
      (i < sfpStart ? copper : sfp).appendChild(div);
    }
  }

  // Simplified _find function as most entities are now found by entity_id suffix
  _find(keyword) {
    return this._entities[keyword];
  }

  getCardSize() {
    return this._config.compact_mode ? 5 : 8;
  }
}

// ---------------------------------------------
// EDITOR (No changes needed, but included for completeness)
// ---------------------------------------------
class SwitchPortCardProEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;
    if (!hass) return;

    // Use hass.devices.device_registry and hass.entities.entity_registry to get more reliable lists
    // This is simplified based on the original editor code.

    const devices = Object.values(hass.devices);
    const entities = Object.keys(hass.states)
      .filter(e => e.includes("bandwidth") || e.includes("_port_"))
      .sort();

    this.innerHTML = `
      <style>
        .row { margin: 12px 0; display: flex; align-items: center; gap: 12px; }
        label { min-width: 160px; font-weight: 500; }
        select, input { flex: 1; max-width: 300px; padding: 8px; border-radius: 6px; border: 1px solid #666; background: #333; color: white; }
        .checkbox { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
        .checkbox input { max-width: 20px; }
      </style>
      <div style="padding: 12px;">
        <div class="row">
          <label>Title</label>
          <input type="text" data-key="name" value="${this._config.name || ''}">
        </div>

        <div class="row">
          <label>Device (Recommended)</label>
          <select data-key="device">
            <option value="">-- Select device --</option>
            ${devices.map(d => `
              <option value="${d.id}" ${d.id === this._config.device ? 'selected' : ''}>
                ${d.name_by_user || d.name || d.id}
              </option>
            `).join('')}
          </select>
        </div>

        <div class="row">
          <label>Or Entity Fallback</label>
          <select data-key="entity">
            <option value="">-- Optional --</option>
            ${entities.map(e => `
              <option value="${e}" ${e === this._config.entity ? 'selected' : ''}>
                ${hass.states[e].attributes?.friendly_name || e}
              </option>
            `).join('')}
          </select>
        </div>

        <div class="row">
          <label>Total Ports</label>
          <input type="number" min="1" max="256" data-key="total_ports" value="${this._config.total_ports || 28}">
        </div>

        <div class="row">
          <label>First SFP Port</label>
          <input type="number" min="1" max="256" data-key="sfp_start_port" value="${this._config.sfp_start_port || 25}">
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="show_total_bandwidth" ${this._config.show_total_bandwidth !== false ? 'checked' : ''}>
          <label>Show Bandwidth Gauge</label>
        </div>

        <div class="row" id="bw-row" style="${this._config.show_total_bandwidth !== false ? '' : 'display:none;'}">
          <label>Max Bandwidth (Gbps)</label>
          <input type="number" step="10" min="1" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps || 100}">
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="compact_mode" ${this._config.compact_mode ? 'checked' : ''}>
          <label>Compact Mode</label>
        </div>
      </div>
    `;

    this.querySelectorAll("[data-key]").forEach(el => {
      el.addEventListener("change", () => {
        const key = el.dataset.key;
        let val = el.type === "checkbox" ? el.checked : el.value;
        if (el.type === "number") val = parseInt(val) || 0;

        const newConfig = { ...this._config, [key]: val };

        if (key === "show_total_bandwidth") {
          this.querySelector("#bw-row").style.display = val ? "flex" : "none";
        }

        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: newConfig },
            bubbles: true,
            composed: true,
          })
        );
      });
    });
  }
}

customElements.define("switch-port-card-pro", SwitchPortCardPro);
customElements.define("switch-port-card-pro-editor", SwitchPortCardProEditor);
