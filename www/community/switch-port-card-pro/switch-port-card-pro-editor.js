class SwitchPortCardPro extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    if (!config.device && !config.entity) {
      throw new Error("Please specify 'device' or 'entity'");
    }
    this._config = config;
  }

  set hass(hass) {
    this._hass = hass;

    // Find device entities from device or from one entity
    let entities = new Set();
    if (this._config.device) {
      const deviceId = this._config.device;
      Object.keys(hass.states).forEach((entityId) => {
        const entity = hass.states[entityId];
        if (entity.attributes?.device_id === deviceId) {
          entities.add(entityId);
        }
      });
    } else if (this._config.entity) {
      const mainEntity = hass.states[this._config.entity];
      if (!mainEntity) return;
      const deviceId = mainEntity.attributes?.device_id;
      if (deviceId) {
        Object.keys(hass.states).forEach((entityId) => {
          if (hass.states[entityId].attributes?.device_id === deviceId) {
            entities.add(entityId);
          }
        });
      } else {
        // Fallback: assume same naming pattern
        const prefix = this._config.entity.split("_total_bandwidth")[0];
        Object.keys(hass.states).forEach((eid) => {
          if (eid.startsWith(prefix)) entities.add(eid);
        });
      }
    }

    this.entities = Object.fromEntries(
      Array.from(entities).map((eid) => [eid, hass.states[eid]])
    );

    if (!this.content) {
      this._renderSkeleton();
    }
    this._render();
  }

  _renderSkeleton() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          background: var(--card-background-color, white);
          border-radius: 12px;
          font-family: var(--primary-font-family);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
          font-size: 1.4em;
          font-weight: 500;
        }
        .system-info {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
          gap: 12px;
          margin: 16px 0;
          font-size: 0.9em;
        }
        .info-item {
          background: var(--secondary-background-color);
          padding: 8px;
          border-radius: 8px;
          text-align: center;
        }
        .gauge {
          width: 100%;
          height: 16px;
          background: #e0e0e0;
          border-radius: 8px;
          overflow: hidden;
          margin: 12px 0;
        }
        .gauge-fill {
          height: 100%;
          background: linear-gradient(90deg, #43a047, #ffb300, #e53935);
          width: 0%;
          transition: width 0.8s ease;
        }
        .ports {
          display: grid;
          grid-template-columns: repeat(14, 1fr);
          gap: 6px;
          margin-top: 16px;
        }
        .port {
          aspect-ratio: 1.8;
          background: #ddd;
          border-radius: 6px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          font-size: 0.75em;
          font-weight: bold;
          color: #333;
          position: relative;
        }
        .port.up-10g    { background: #1b5e20; color: white; }
        .port.up-5g     { background: #388e3c; color: white; }
        .port.up-2_5g   { background: #66bb6a; color: black; }
        .port.up-1g     { background: #a5d6a7; color: black; }
        .port.up-100m   { background: #fff176; color: black; }
        .port.up-10m    { background: #ffeb3b; color: black; }
        .port.down      { background: #424242; color: #888; }
        .port.sfp       { border: 2px solid #1976d2; }
        .port-label {
          position: absolute;
          bottom: 2px;
          font-size: 0.6em;
          opacity: 0.9;
        }
        .compact .ports { grid-template-columns: repeat(7, 1fr); }
        .compact .port { font-size: 0.65em; }
        @media (max-width: 600px) {
          .ports { grid-template-columns: repeat(7, 1fr); }
        }
      </style>
      <div class="card-content">
        <div class="header">
          <span id="title"></span>
          <span id="status"></span>
        </div>
        <div class="system-info" id="system-info"></div>
        <div class="gauge" id="gauge" style="display:none">
          <div class="gauge-fill" id="gauge-fill"></div>
        </div>
        <div class="ports ${this._config.compact_mode ? 'compact' : ''}" id="ports"></div>
      </div>
    `;
    this.content = true;
  }

  _render() {
    if (!this.entities || Object.keys(this.entities).length === 0) {
      this.shadowRoot.querySelector(".card-content").innerHTML = "<p>No data found. Check device/entity.</p>";
      return;
    }

    const bandwidthEnt = Object.values(this.entities).find(e => 
      e.attributes?.friendly_name?.toLowerCase().includes("bandwidth")
    );
    const cpuEnt = Object.values(this.entities).find(e => 
      e.attributes?.friendly_name?.toLowerCase().includes("cpu")
    );
    const memEnt = Object.values(this.entities).find(e => 
      e.attributes?.friendly_name?.toLowerCase().includes("memory")
    );
    const uptimeEnt = Object.values(this.entities).find(e => 
      e.attributes?.friendly_name?.toLowerCase().includes("uptime")
    );
    const hostnameEnt = Object.values(this.entities).find(e => 
      e.attributes?.friendly_name?.toLowerCase().includes("hostname")
    );

    // Header
    this.shadowRoot.getElementById("title").textContent = this._config.name || hostnameEnt?.state || "Switch";
    this.shadow.getElementById("status").textContent = bandwidthEnt ? `${bandwidthEnt.state} Mbps` : "—";

    // System info
    const sysDiv = this.shadow.getElementById("system-info");
    sysDiv.innerHTML = `
      ${cpuEnt ? `<div class="info-item">CPU<br><strong>${cpuEnt.state}%</strong></div>` : ''}
      ${memEnt ? `<div class="info-item">RAM<br><strong>${memEnt.state}%</strong></div>` : ''}
      ${uptimeEnt ? `<div class="info-item">Uptime<br><strong>${uptimeEnt.state} h</strong></div>` : ''}
    `;

    // Gauge
    if (this._config.show_total_bandwidth !== false && bandwidthEnt) {
      const gauge = this.shadow.getElementById("gauge");
      const fill = this.shadow.getElementById("gauge-fill");
      gauge.style.display = "block";
      const max = (this._config.max_bandwidth_gbps || 100) * 1000;
      const percent = Math.min((parseFloat(bandwidthEnt.state) / max) * 100, 100);
      fill.style.width = `${percent}%`;
    }

    // Ports
    const portsDiv = this.shadow.getElementById("ports");
    portsDiv.innerHTML = "";
    const totalPorts = this._config.total_ports || 28;
    const sfpStart = this._config.sfp_start_port || 25;

    for (let i = 1; i <= totalPorts; i++) {
      const portEnt = Object.values(this.entities).find(e => 
        e.attributes?.friendly_name?.toLowerCase().includes(`port ${i}`)
      );
      const state = portEnt?.state || "unknown";
      const isUp = state === "up";
      const speed = portEnt?.attributes?.speed || "unknown";

      const portDiv = document.createElement("div");
      portDiv.className = `port ${isUp ? 'up-${speed}` : "down"} ${i >= sfpStart ? "sfp" : ""}`;

      let speedLabel = "";
      if (isUp) {
        if (speed.includes("10G")) speedLabel = "10G";
        else if (speed.includes("5G")) speedLabel = "5G";
        else if (speed.includes("2.5G")) speedLabel = "2.5G";
        else if (speed.includes("1G")) speedLabel = "1G";
        else if (speed.includes("100")) speedLabel = "100M";
        else if (speed.includes("10")) speedLabel = "10M";
      }

      portDiv.innerHTML = `
        <div>${i}</div>
        <div class="port-label">${isUp ? speedLabel : "DOWN"}</div>
      `;
      portsDiv.appendChild(portDiv);
    }

    // Layout: even ports on top?
    if (this._config.even_ports_on_top) {
      const children = Array.from(portsDiv.children);
      const reordered = [];
      for (let i = 0; i < children.length / 2; i++) {
        reordered.push(children[i*2 + 1] || children[i*2]);
        reordered.push(children[i*2] || children[i*2 + 1]);
      }
      portsDiv.innerHTML = "";
      reordered.forEach(c => portsDiv.appendChild(c));
    }
  }

  getCardSize() {
    return this._config.compact_mode ? 4 : 7;
  }
}

customElements.define("switch-port-card-pro", SwitchPortCardPro);

// ──────────────────────────────────────────────
// Editor
// ──────────────────────────────────────────────
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

    const devices = Object.keys(this._hass.devices);
    const entities = Object.keys(this._hass.states);

    this.innerHTML = `
      <style>
        .container { padding: 12px; }
        .row { margin: 12px 0; display: flex; align-items: center; gap: 12px; }
        label { width: 160px; font-weight: 500; }
        input, select { flex: 1; padding: 8px; border-radius: 4px; border: 1px solid #ccc; }
        .checkbox { display: flex; align-items: center; gap: 8px; }
      </style>
      <div class="container">
        <div class="row">
          <label>Card Title</label>
          <input type="text" data-key="name" value="${this._config.name || ''}">
        </div>

        <div class="row">
          <label>Device (Recommended)</label>
          <select data-key="device">
            <option value="">-- Select device --</option>
            ${devices.map(id => `
              <option value="${id}" ${id === this._config.device ? 'selected' : ''}>
                ${this._hass.devices[id]?.name_by_user || this._hass.devices[id]?.name || id}
              </option>
            `).join('')}
          </select>
        </div>

        <div class="row">
          <label>Or pick one entity</label>
          <select data-key="entity">
            <option value="">-- Optional fallback --</option>
            ${entities
              .filter(e => e.includes("bandwidth") || e.includes("port_"))
              .map(e => `<option value="${e}" ${e === this._config.entity ? 'selected' : ''}>${this._hass.states[e].attributes.friendly_name || e}</option>`)
              .join('')}
          </select>
        </div>

        <div class="row">
          <label>Total Ports</label>
          <input type="number" min="1" max="128" data-key="total_ports" value="${this._config.total_ports || 28}">
        </div>

        <div class="row">
          <label>First SFP+ Port</label>
          <input type="number" min="1" max="128" data-key="sfp_start_port" value="${this._config.sfp_start_port || 25}">
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="show_total_bandwidth" ${this._config.show_total_bandwidth !== false ? 'checked' : ''}>
          <label>Show Bandwidth Gauge</label>
        </div>

        <div class="row" style="margin-left:180px;display:${this._config.show_total_bandwidth !== false ? 'flex' : 'none'}" id="maxbw">
          <label>Max Bandwidth (Gbps)</label>
          <input type="number" step="10" min="10" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps || 100}">
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
        if (e.target.type === "checkbox") value = e.target.checked;
        if (e.target.type === "number") value = parseInt(value) || 0;

        const newConfig = { ...this._config, [key]: value };
        if (!e.target.checked && key === "show_total_bandwidth") {
          delete newConfig.max_bandwidth_gbps;
        }

        this._config = newConfig;
        this.dispatchEvent(new Event("config-changed", { bubbles: true, composed: true, detail: { config: newConfig } }));
      });
    });

    // Sync gauge row visibility
    const gaugeCheck = this.querySelector('[data-key="show_total_bandwidth"]');
    const gaugeRow = this.querySelector('#maxbw');
    gaugeCheck.addEventListener('change', () => {
      gaugeRow.style.display = gaugeCheck.checked ? 'flex' : 'none';
    });
  }
}

customElements.define("switch-port-card-pro-editor", SwitchPortCardProEditor);
