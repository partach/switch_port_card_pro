// switch-port-card-pro.js
class SwitchPortCardPro extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    if (!config.device && !config.entity) {
      throw new Error("Please specify 'device' or 'entity'");
    }
    this._config = { ...config };
  }

  set hass(hass) {
    this._hass = hass;
    this._entities = this._collectEntities();
    if (!this._root) this._createSkeleton();
    this._render();
  }

  _collectEntities() {
    const entities = {};

    if (this._config.device) {
      const deviceId = this._config.device;
      Object.values(this._hass.states).forEach(entity => {
        if (entity.attributes.device_id === deviceId) {
          entities[entity.entity_id] = entity;
        }
      });
    } else {
      // Fallback via one entity
      const main = this._hass.states[this._config.entity];
      if (!main) return entities;
      const deviceId = main.attributes.device_id;
      if (deviceId) {
        Object.values(this._hass.states).forEach(entity => {
          if (entity.attributes.device_id === deviceId) {
            entities[entity.entity_id] = entity;
          }
        });
      }
    }
    return entities;
  }

  _createSkeleton() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          background: var(--card-background-color, #1e1e1e);
          color: var(--primary-text-color, #fff);
          padding: 16px;
          border-radius: 16px;
          font-family: var(--ha-font-family, Roboto);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          font-size: 1.5em;
          font-weight: 600;
        }
        .system-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
          gap: 12px;
          margin: 16px 0;
        }
        .info-box {
          background: rgba(255,255,255,0.08);
          padding: 10px;
          border-radius: 10px;
          text-align: center;
          border-left: 4px solid #2196f3;
        }
        .info-value { font-size: 1.4em; font-weight: bold; }
        .info-label { font-size: 0.8em; opacity: 0.8; }
        .gauge {
          height: 24px;
          background: #333;
          border-radius: 12px;
          overflow: hidden;
          margin: 16px 0;
          display: none;
        }
        .gauge-fill {
          height: 100%;
          background: linear-gradient(90deg, #4caf50, #ff9800, #f44336);
          width: 0%;
          transition: width 0.8s ease;
        }
        .ports-section { margin-top: 20px; }
        .section-label {
          font-size: 0.9em;
          font-weight: 600;
          color: #aaa;
          margin: 16px 0 8px;
        }
        .ports-grid {
          display: grid;
          grid-template-columns: repeat(14, 1fr);
          gap: 6px;
        }
        .port {
          aspect-ratio: 2.2 / 1;
          background: #333;
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
          border: 1px solid rgba(255,255,255,0.1);
        }
        .port:hover { transform: scale(1.08); z-index: 10; }
        .port-num { font-size: 0.9em; }
        .port-status { font-size: 0.7em; margin-top: 2px; }

        /* Speed classes */
        .port.up-10g   { background: #0d47a1; color: white; }
        .port.up-5g    { background: #1565c0; color: white; }
        .port.up-2_5g  { background: #1976d2; color: white; }
        .port.up-1g    { background: #1b5e20; color: white; }
        .port.up-100m  { background: #f57f17; color: white; }
        .port.up-10m   { background: #e65100; color: white; }
        .port.down     { background: #424242; color: #888; opacity: 0.7; }
        .port.sfp      { border: 2px solid #2196f3; box-shadow: 0 0 8px #2196f333; }

        .compact .ports-grid { grid-template-columns: repeat(7, 1fr); }
        .compact .port { font-size: 0.65em; }

        @media (max-width: 600px) {
          .ports-grid { grid-template-columns: repeat(7, 1fr); }
        }
      </style>

      <div class="header">
        <span id="title">Switch</span>
        <span id="bandwidth">— Mbps</span>
      </div>

      <div class="system-grid" id="system"></div>

      <div class="gauge" id="gauge"><div class="gauge-fill" id="fill"></div></div>

      <div class="ports-section ${this._config.compact_mode ? 'compact' : ''}">
        <div class="section-label">COPPER PORTS</div>
        <div class="ports-grid" id="copper"></div>
        <div class="section-label">SFP+ PORTS</div>
        <div class="ports-grid" id="sfp"></div>
      </div>
    `;
    this._root = true;
  }

  _render() {
    if (Object.keys(this._entities).length === 0) {
      this.shadowRoot.querySelector(".header").innerHTML = `<span style="color:#f44336">No device found</span>`;
      return;
    }

    const bw = this._find("bandwidth") || this._find("total_bandwidth");
    const cpu = this._find("cpu");
    const mem = this._find("memory");
    const uptime = this._find("uptime");
    const host = this._find("hostname") || this._find("host");

    // Header
    this.shadowRoot.getElementById("title").textContent = this._config.name || host?.state || "Switch";
    this.shadowRoot.getElementById("bandwidth").textContent = bw ? `${Number(bw.state).toFixed(1)} Mbps` : "—";

    // System info
    const sys = this.shadowRoot.getElementById("system");
    sys.innerHTML = `
      ${cpu ? `<div class="info-box"><div class="info-value">${Math.round(cpu.state)}%</div><div class="info-label">CPU</div></div>` : ''}
      ${mem ? `<div class="info-box"><div class="info-value">${Math.round(mem.state)}%</div><div class="info-label">Memory</div></div>` : ''}
      ${uptime ? `<div class="info-box"><div class="info-value">${Number(uptime.state).toFixed(1)}</div><div class="info-label">Uptime (h)</div></div>` : ''}
      ${host ? `<div class="info-box"><div class="info-value">${host.state}</div><div class="info-label">Host</div></div>` : ''}
    `;

    // Gauge
    if (this._config.show_total_bandwidth !== false && bw) {
      const gauge = this.shadowRoot.getElementById("gauge");
      gauge.style.display = "block";
      const max = (this._config.max_bandwidth_gbps || 100) * 1000;
      const pct = Math.min((bw.state / max) * 100, 100);
      this.shadowRoot.getElementById("fill").style.width = pct + "%";
    }

    // Ports
    const total = this._config.total_ports || 28;
    const sfpStart = this._config.sfp_start_port || 25;
    const copper = this.shadowRoot.getElementById("copper");
    const sfp = this.shadowRoot.getElementById("sfp");
    copper.innerHTML = ""; sfp.innerHTML = "";

    for (let i = 1; i <= total; i++) {
      const portEnt = this._find(`port_${i}`) || this._find(`port ${i}`);
      const status = portEnt?.state === "up" || portEnt?.state === "on" ? "up" : "down";
      const speed = portEnt?.attributes?.speed || "0";
      let speedClass = status === "down" ? "down" : "up-1g";

      if (status === "up") {
        if (speed.includes("10G")) speedClass = "up-10g";
        else if (speed.includes("5G")) speedClass = "up-5g";
        else if (speed.includes("2.5G")) speedClass = "up-2_5g";
        else if (speed.includes("1G")) speedClass = "up-1g";
        else if (speed.includes("100")) speedClass = "up-100m";
        else if (speed.includes("10")) speedClass = "up-10m";
      }

      const div = document.createElement("div");
      div.className = `port ${speedClass} ${i >= sfpStart ? "sfp" : ""}`;
      div.title = `${portEnt?.attributes?.friendly_name || `Port ${i}`}\nSpeed: ${speed || "—"}`;
      div.innerHTML = `
        <div class="port-num">${i}</div>
        <div class="port-status">${status === "up" ? "ON" : "OFF"}</div>
      `;
      (i < sfpStart ? copper : sfp).appendChild(div);
    }
  }

  _find(keyword) {
    return Object.values(this._entities).find(e =>
      e.entity_id.toLowerCase().includes(keyword) ||
      (e.attributes.friendly_name || "").toLowerCase().includes(keyword)
    );
  }

  getCardSize() {
    return this._config.compact_mode ? 5 : 8;
  }
}

// Editor — pure 2025 device picker
class SwitchPortCardProEditor extends HTMLElement {
  setConfig(config) { this._config = config; }
  set hass(hass) {
    this._hass = hass;
    if (!hass) return;
    const devices = Object.values(hass.devices);
    const entities = Object.keys(hass.states);

    this.innerHTML = `
      <style>
        .row { margin: 12px 0; display: flex; align-items: center; gap: 12px; }
        label { width: 160px; font-weight: 500; }
        select, input { flex: 1; padding: 8px; border-radius: 6px; border: 1px solid #666; background: #333; color: white; }
        .checkbox { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
      </style>
      <div class="row"><label>Title</label><input data-key="name" value="${this._config.name || ''}"></div>
      <div class="row">
        <label>Device (best)</label>
        <select data-key="device">
          <option value="">-- Pick device --</option>
          ${devices.map(d => `<option value="${d.id}" ${d.id===this._config.device?'selected':''}>
            ${d.name_by_user || d.name || d.id}
          </option>`).join('')}
        </select>
      </div>
      <div class="row"><label>or Entity</label>
        <select data-key="entity">
          <option value="">-- optional fallback --</option>
          ${entities.filter(e=>e.includes("bandwidth")||e.includes("port_")).map(e=>`
            <option value="${e}" ${e===this._config.entity?'selected':''}>
              ${this._hass.states[e].attributes.friendly_name || e}
            </option>`).join('')}
        </select>
      </div>
      <div class="row"><label>Total Ports</label><input type="number" data-key="total_ports" value="${this._config.total_ports||28}"></div>
      <div class="row"><label>SFP starts at</label><input type="number" data-key="sfp_start_port" value="${this._config.sfp_start_port||25}"></div>
      <div class="checkbox"><input type="checkbox" data-key="show_total_bandwidth" ${this._config.show_total_bandwidth!==false?'checked':''}><label>Show Bandwidth Gauge</label></div>
      <div class="row" style="margin-left:172px;${this._config.show_total_bandwidth===false?'display:none':''}" id="maxbw">
        <label>Max Gbps</label><input type="number" step="10" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps||100}">
      </div>
      <div class="checkbox"><input type="checkbox" data-key="compact_mode" ${this._config.compact_mode?'checked':''}><label>Compact Mode</label></div>
    `;

    this.querySelectorAll("[data-key]").forEach(el => {
      el.addEventListener("change", () => {
        const key = el.dataset.key;
        let val = el.type === "checkbox" ? el.checked : el.value;
        if (el.type === "number") val = parseInt(val) || 0;
        const newConf = { ...this._config, [key]: val };
        if (key === "show_total_bandwidth") {
          this.querySelector("#maxbw").style.display = val ? "flex" : "none";
        }
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: newConf }, bubbles: true, composed: true }));
      });
    });
  }
}

customElements.define("switch-port-card-pro", SwitchPortCardPro);
customElements.define("switch-port-card-pro-editor", SwitchPortCardProEditor);
