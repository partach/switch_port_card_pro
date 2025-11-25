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
      name: "Switch Ports",
      entity_prefix: "sensor.mainswitch",
      total_ports: 28,
      sfp_start_port: 25,
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      compact_mode: false,
      even_ports_on_top: false,
    };
  }

  setConfig(config) {
    if (!config.entity_prefix) {
      throw new Error("entity_prefix is required (e.g., 'sensor.mainswitch')");
    }
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;
    
    // Build entity map from prefix
    this.entities = this._getEntitiesByPrefix();

    if (!this.content) {
      this._renderSkeleton();
    }
    this._render();
  }

  _getEntitiesByPrefix() {
    const prefix = this._config.entity_prefix || "sensor.mainswitch";
    const entities = {};

    Object.keys(this._hass.states).forEach((eid) => {
      if (eid.startsWith(prefix)) {
        entities[eid] = this._hass.states[eid];
      }
    });

    return entities;
  }

  _renderSkeleton() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          background: var(--card-background-color, #1e1e1e);
          border-radius: 12px;
          font-family: var(--primary-font-family);
          color: var(--primary-text-color, #fff);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          font-size: 1.4em;
          font-weight: 600;
        }
        .system-info {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
          gap: 12px;
          margin: 16px 0;
          font-size: 0.85em;
        }
        .info-item {
          background: var(--secondary-background-color, #333);
          padding: 8px 12px;
          border-radius: 8px;
          text-align: center;
          border-left: 3px solid #2196f3;
        }
        .gauge {
          width: 100%;
          height: 20px;
          background: #424242;
          border-radius: 10px;
          overflow: hidden;
          margin: 12px 0;
          display: none;
        }
        .gauge-fill {
          height: 100%;
          background: linear-gradient(90deg, #4caf50, #ffb300, #f44336);
          width: 0%;
          transition: width 0.5s ease;
        }
        .ports-section {
          margin-top: 20px;
        }
        .ports-label {
          font-size: 0.9em;
          color: #999;
          margin-bottom: 8px;
          font-weight: 600;
        }
        .ports {
          display: grid;
          grid-template-columns: repeat(14, 1fr);
          gap: 4px;
        }
        .port {
          aspect-ratio: 2.2;
          border-radius: 6px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          font-size: 0.7em;
          font-weight: 600;
          cursor: pointer;
          transition: transform 0.2s ease;
          border: 1px solid rgba(255,255,255,0.1);
        }
        .port:hover {
          transform: scale(1.05);
        }
        .port-num {
          font-size: 0.8em;
          opacity: 0.9;
        }
        .port-status {
          font-size: 0.65em;
          margin-top: 2px;
        }
        /* States */
        .port.on-10g    { background: #0d47a1; color: #fff; }
        .port.on-1g     { background: #1b5e20; color: #fff; }
        .port.on-100m   { background: #f57f17; color: #fff; }
        .port.on-10m    { background: #ff6f00; color: #fff; }
        .port.on        { background: #616161; color: #fff; }
        .port.off       { background: #303030; color: #666; opacity: 0.6; }
        .port.sfp       { border: 2px solid #2196f3; }
        
        .compact .ports { grid-template-columns: repeat(7, 1fr); }
        .compact .port { font-size: 0.65em; }
        
        @media (max-width: 600px) {
          .ports { grid-template-columns: repeat(7, 1fr); }
          .header { font-size: 1.2em; }
        }
      </style>
      <div class="card-content">
        <div class="header">
          <span id="title"></span>
          <span id="status"></span>
        </div>
        <div class="system-info" id="system-info"></div>
        <div class="gauge" id="gauge">
          <div class="gauge-fill" id="gauge-fill"></div>
        </div>
        <div class="ports-section">
          <div class="ports-label">COPPER PORTS</div>
          <div class="ports" id="copper-ports"></div>
          <div class="ports-label" style="margin-top:16px;">SFP+ PORTS</div>
          <div class="ports" id="sfp-ports"></div>
        </div>
      </div>
    `;
    this.content = true;
  }

  _render() {
    if (!this.entities || Object.keys(this.entities).length === 0) {
      this.shadowRoot.querySelector(".card-content").innerHTML = 
        `<p style="color: #f44336;">No entities found. Check entity_prefix: ${this._config.entity_prefix}</p>`;
      return;
    }

    // Find key entities
    const bandwidth = this._findEntity("bandwidth");
    const cpu = this._findEntity("cpu");
    const memory = this._findEntity("memory");
    const uptime = this._findEntity("uptime");
    const hostname = this._findEntity("hostname");

    // Header
    this.shadowRoot.getElementById("title").textContent = 
      this._config.name || hostname?.state || "Switch Ports";
    this.shadowRoot.getElementById("status").textContent = 
      bandwidth ? `${parseFloat(bandwidth.state).toFixed(1)} Mbps` : "—";

    // System info
    const sysDiv = this.shadowRoot.getElementById("system-info");
    sysDiv.innerHTML = `
      ${cpu ? `<div class="info-item"><strong>${parseFloat(cpu.state).toFixed(0)}%</strong><br>CPU</div>` : ''}
      ${memory ? `<div class="info-item"><strong>${parseFloat(memory.state).toFixed(0)}%</strong><br>Memory</div>` : ''}
      ${uptime ? `<div class="info-item"><strong>${parseFloat(uptime.state).toFixed(1)}</strong><br>Uptime (h)</div>` : ''}
      ${hostname ? `<div class="info-item"><strong>${hostname.state}</strong><br>Host</div>` : ''}
    `;

    // Bandwidth gauge
    if (this._config.show_total_bandwidth !== false && bandwidth) {
      const gauge = this.shadowRoot.getElementById("gauge");
      gauge.style.display = "block";
      const maxBps = (this._config.max_bandwidth_gbps || 100) * 1000;
      const percent = Math.min((parseFloat(bandwidth.state) / maxBps) * 100, 100);
      this.shadowRoot.getElementById("gauge-fill").style.width = `${percent}%`;
    }

    // Render ports
    this._renderPorts();
  }

  _renderPorts() {
    const totalPorts = this._config.total_ports || 28;
    const sfpStart = this._config.sfp_start_port || 25;
    const copperDiv = this.shadowRoot.getElementById("copper-ports");
    const sfpDiv = this.shadowRoot.getElementById("sfp-ports");

    copperDiv.innerHTML = "";
    sfpDiv.innerHTML = "";

    for (let i = 1; i <= totalPorts; i++) {
      const portEntity = this._findEntity(`port_${i}`);
      const state = portEntity?.state || "unknown";
      const description = portEntity?.attributes?.description || "";

      // Determine speed from separate speed sensor
      const speedEntity = this._findEntity(`port_speed_${i}`);
      const speed = speedEntity?.state || "0";
      const speedBps = parseInt(speed);

      let speedClass = "on";
      if (state === "off" || state === "down") {
        speedClass = "off";
      } else if (speedBps >= 10000000000) {
        speedClass = "on-10g";
      } else if (speedBps >= 1000000000) {
        speedClass = "on-1g";
      } else if (speedBps >= 100000000) {
        speedClass = "on-100m";
      } else if (speedBps >= 10000000) {
        speedClass = "on-10m";
      }

      const portDiv = document.createElement("div");
      portDiv.className = `port ${speedClass} ${i >= sfpStart ? "sfp" : ""}`;
      portDiv.title = `Port ${i}\n${description || "No description"}\nState: ${state}`;
      portDiv.innerHTML = `
        <div class="port-num">${i}</div>
        <div class="port-status">${state === "on" ? "✓" : "×"}</div>
      `;

      if (i < sfpStart) {
        copperDiv.appendChild(portDiv);
      } else {
        sfpDiv.appendChild(portDiv);
      }
    }
  }

  _findEntity(keyword) {
    return Object.values(this.entities).find(e =>
      e.attributes?.friendly_name?.toLowerCase().includes(keyword.toLowerCase()) ||
      e.entity_id?.toLowerCase().includes(keyword.toLowerCase())
    );
  }

  getCardSize() {
    return this._config.compact_mode ? 4 : 6;
  }
}

// ─────────────────────────────────────────────
// EDITOR
// ─────────────────────────────────────────────
class SwitchPortCardProEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass) return;

    const sensorEntities = Object.keys(this._hass.states)
      .filter(e => e.startsWith("sensor."))
      .sort();

    this.innerHTML = `
      <style>
        .container { padding: 16px; font-family: var(--primary-font-family); }
        .row { margin: 12px 0; display: flex; align-items: center; gap: 12px; }
        label { min-width: 160px; font-weight: 500; }
        input, select { flex: 1; max-width: 300px; padding: 8px; border-radius: 4px; border: 1px solid #ccc; }
        .checkbox { display: flex; align-items: center; gap: 8px; margin: 12px 0; }
        .checkbox input { max-width: 20px; }
      </style>
      <div class="container">
        <div class="row">
          <label>Card Title</label>
          <input type="text" data-key="name" value="${this._config.name || 'Switch Ports'}" placeholder="My Switch">
        </div>

        <div class="row">
          <label>Entity Prefix</label>
          <select data-key="entity_prefix">
            <option value="">-- Select entity --</option>
            ${sensorEntities
              .filter(e => e.includes("bandwidth") || e.includes("port_"))
              .map(e => {
                const base = e.split("_total_bandwidth")[0] || e.split("_port_")[0];
                return `<option value="${base}" ${base === this._config.entity_prefix ? 'selected' : ''}>${base}</option>`;
              })
              .filter((v, i, a) => a.indexOf(v) === i)
              .map(v => `<option value="${v}" ${v === this._config.entity_prefix ? 'selected' : ''}>${v}</option>`)
              .join('')}
          </select>
        </div>

        <div class="row">
          <label>Total Ports</label>
          <input type="number" min="1" max="128" data-key="total_ports" value="${this._config.total_ports || 28}">
        </div>

        <div class="row">
          <label>First SFP Port</label>
          <input type="number" min="1" max="128" data-key="sfp_start_port" value="${this._config.sfp_start_port || 25}">
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="show_total_bandwidth" ${this._config.show_total_bandwidth !== false ? 'checked' : ''}>
          <label>Show Bandwidth Gauge</label>
        </div>

        <div class="row" id="bw-row" style="${this._config.show_total_bandwidth !== false ? '' : 'display:none;'}">
          <label>Max Bandwidth (Gbps)</label>
          <input type="number" min="1" step="10" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps || 100}">
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="compact_mode" ${this._config.compact_mode ? 'checked' : ''}>
          <label>Compact Mode</label>
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="even_ports_on_top" ${this._config.even_ports_on_top ? 'checked' : ''}>
          <label>Even ports on top row</label>
        </div>
      </div>
    `;

    this.querySelectorAll("input, select").forEach((el) => {
      el.addEventListener("change", (e) => {
        const key = e.target.dataset.key;
        let value = e.target.value;

        if (e.target.type === "checkbox") {
          value = e.target.checked;
        } else if (e.target.type === "number") {
          value = parseInt(value) || 0;
        }

        this._config = { ...this._config, [key]: value };

        // Toggle bandwidth row visibility
        if (key === "show_total_bandwidth") {
          this.querySelector("#bw-row").style.display = value ? "flex" : "none";
        }

        this.dispatchEvent(
          new Event("config-changed", { bubbles: true, composed: true, detail: { config: this._config } })
        );
      });
    });
  }
}

customElements.define("switch-port-card-pro", SwitchPortCardPro);
customElements.define("switch-port-card-pro-editor", SwitchPortCardProEditor);
