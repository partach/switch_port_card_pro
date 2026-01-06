// switch-port-card-pro.js
const DEFAULT_CONFIG = {
  type: "custom:switch-port-card-pro",
  name: "Network Switch",
  device: "",
  entity: "",
  total_ports: 8,
  sfp_start_port: 9,
  custom_text: "Custom Value",
  custom_port_text: "Custom Port Val.",
  show_total_bandwidth: true,
  max_bandwidth_gbps: 100,
  compact_mode: false,
  show_port_type_labels: true,
  row2: "rx_tx_live",
  row3: "speed",
  color_scheme: "speed",
  port_size: "medium",
  ports_per_row: 8,
  hide_unused_port: false,
  hide_unused_port_hours: 24,
  layout_mode: "linear",  // Options: "linear" (default), "even_top", "odd_top"
  truncate_text: true,
  theme_safe_colors: true,  // not used for now
  card_background_color: "rgba(var(--rgb-primary-background-color, 40, 40, 40), 0.6)",
  system_boxes: {
    cpu: true,
    memory: true,
    uptime: true,
    hostname: true,
    poe: true,
    firmware: true,
    custom: true,
  },
  system_box_overrides: {
    cpu: "",
    memory: "",
    uptime: "",
    hostname: "",
    poe: "",
    firmware: "",
    custom: "",
  },
};

class SwitchPortCardPro extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  static getConfigElement() {
    return document.createElement("switch-port-card-pro-editor");
  }

  static getStubConfig() {
    return { ...DEFAULT_CONFIG };
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Invalid configuration");
    }

    this._config = {
      ...DEFAULT_CONFIG,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;

    if (!this._config) {
      console.warn("switch-port-card-pro: config not set yet");
      return;
    }

    if (!this._entities || this._lastHass !== hass) {
      this._entities = this._collectEntities(hass);
      this._lastHass = hass;
    }

    if (!this.shadowRoot.querySelector("ha-card")) {
      this._createSkeleton();
    }
    // Handle ha-entity-picker changes
    this.querySelectorAll("ha-entity-picker").forEach(picker => {
      picker.addEventListener("value-changed", (ev) => {
        const key = picker.configValue;  // e.g. "system_box_overrides.cpu"
        const value = ev.detail.value || "";

        const newConfig = structuredClone(this._config);
        const keys = key.split(".");
        let target = newConfig;
        for (let i = 0; i < keys.length - 1; i++) {
          target = target[keys[i]] = target[keys[i]] || {};
        }
        target[keys[keys.length - 1]] = value;

        this._config = newConfig;
        this.dispatchEvent(new CustomEvent("config-changed", {
          detail: { config: newConfig },
          bubbles: true,
          composed: true
        }));
      });
    });

    this._render();
  }

  _collectEntities(hass) {
    const entities = {};
    if (!this._config) return entities;

    let searchEntities = [];

    if (this._config.device) {
      const prefix = this._config.device.endsWith('_') ? this._config.device : this._config.device + "_";
      searchEntities = Object.keys(hass.states).filter(id => id.startsWith(prefix));
    }

    if (searchEntities.length === 0 && this._config.entity) {
      const parts = this._config.entity.split("_total_bandwidth");
      if (parts.length > 1) {
        const prefix = parts[0] + "_";
        searchEntities = Object.keys(hass.states).filter(id => id.startsWith(prefix));
      } else {
        searchEntities = [this._config.entity];
      }
    }

    if (searchEntities.length === 0) {
      searchEntities = Object.keys(hass.states);
    }

    searchEntities.forEach(id => {
      if (typeof id !== "string") return;
      const e = hass.states[id];
      if (!e) return;

      if (id.includes("_total_bandwidth")) entities.bandwidth = e;
      else if (id.includes("_system_cpu") || id.includes("cpu_usage")) entities.cpu = e;
      else if (id.includes("_system_memory") || id.includes("memory_usage")) entities.memory = e;
      else if (id.includes("_system_uptime") || id.includes("uptime")) entities.uptime = e;
      else if (id.includes("_system_hostname") || id.includes("hostname")) entities.hostname = e;
      else if (id.includes("_total_poe") || id.includes("total_poe")) entities.total_poe = e;
      else if (id.includes("_custom_value") || id.includes("custom_value")) entities.custom_value = e;
      else if (id.includes("_firmware") || id.includes("firmware")) entities.firmware = e;
      else if (id.includes("_port_") && id.includes("_status")) {
        const m = id.match(/_port_(\d+)_status/);
        if (m) entities[`port_${m[1]}_status`] = e;
      }
    });

    return entities;
  }
  _applyPortsPerRowStaggered() {
    const portsPerRow = this._config.ports_per_row || 8;
    const style = document.createElement('style');
    style.textContent = `:root { --ports-per-row: ${portsPerRow}; }`;
    this.shadowRoot.appendChild(style);
  }
  _applyPortsPerRowToGrid(gridElement) {
    if (!gridElement) return;
    const portsPerRow = this._config.ports_per_row || 8;
    gridElement.style.gridTemplateColumns = `repeat(${portsPerRow}, 1fr)`;
  }
  _createSkeleton() {
    const c = this._config.compact_mode ? "compact" : "";
    const hasRow3 = this._config.row3 && this._config.row3.toLowerCase() !== "none";

    this.shadowRoot.innerHTML = `
      <style>
        .section-hidden {
          display: none !important;
        }
        .section-hidden + .ports-grid {
          margin-top: 1px;
        }
        :host{display:block;color:var(--primary-text-color);padding:1px;border-radius:var(--ha-card-border-radius,12px);font-family:var(--ha-font-family,Roboto)}
        .system-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:6px;margin:10px 0 8px 0}
        .info-box{background:rgba(var(--rgb-card-background-color,255,255,255),0.08);backdrop-filter:blur(8px);padding:7px 9px;border-radius:10px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.12)}
        .info-value{font-size:1.05em;font-weight:bold;line-height:1.05;margin:0}
        .info-label{font-size:0.8em;opacity:0.8;color:var(--secondary-text-color);line-height:1.2;margin-top:1px}
        .info-box.firmware .info-value{font-size:0.6em!important;font-weight:normal!important;line-height:1.3}
        .gauge{height:18px;background:var(--light-primary-color);border-radius:12px;overflow:hidden;margin:18px 0;display:none;position:relative}
        .gauge[style*="display: none"] {
          margin: 0 !important;
          height: 0 !important;
        }
        .gauge-fill {
          background: linear-gradient(90deg, 
            var(--label-badge-green, #4caf50),
            var(--label-badge-yellow, #ff9800) 50%,
            var(--label-badge-red, #f44336)
          );
        }
        .section-label{font-size:0.9em;font-weight:600;color:var(--secondary-text-color);margin:2px 0 4px;text-align:center;width:100%}
        .ports-grid {
          display: grid;
          padding: 2px 0;
          gap: 3px;
          grid-template-columns: repeat(auto-fit, minmax(var(--port-min-width, 50px), 1fr));
          --port-min-width: 50px;
        }

        /* Size-based grid adjustments */
        .ports-grid:has(.port.size-xsmall) { --port-min-width: 38px; }
        .ports-grid:has(.port.size-small) { --port-min-width: 38px; }
        .ports-grid:has(.port.size-medium) { --port-min-width: 50px; }
        .ports-grid:has(.port.size-large) { --port-min-width: 64px; }
        .ports-grid:has(.port.size-xlarge) { --port-min-width: 78px; }

        /* Compact mode overrides */
        .compact .ports-grid { --port-min-width: 40px; }
        .compact .ports-grid:has(.port.size-xlarge) { --port-min-width: 48px; }
        .ports-grid.top-row,
        .ports-grid.bottom-row {
          display: grid;
          grid-template-columns: repeat(var(--ports-per-row, 8), 1fr);
          gap: 3px;
          width: 100%;
          margin-bottom: 6px;  /* Space between top and bottom row */
        }

        .compact .ports-grid.top-row,
        .compact .ports-grid.bottom-row {
          margin-bottom: 4px;
        }
        .port {
          display: flex;
          flex-direction: column;
          justify-content: ${hasRow3 ? 'space-between' : 'flex-start'};
          padding: ${hasRow3 ? '4px 2px 4px 2px' : '4px 2px'} !important;
          gap: 2px;
          border-radius: 4px;
          background: var(--card-background-color, rgba(var(--rgb-card-background-color), 0.8));
          cursor: default;
          transition: none;
          position: relative;
          color: var(--primary-text-color);
          box-shadow: 0 1px 3px rgba(34, 33, 33, 0.2), inset 0 1px 0 rgba(255,255,255,.06);
        }
        #title, #bandwidth {
          color: var(--primary-text-color);
        }
        .port:hover{transform:scale(1.06);z-index:10}
        .header{
          display:flex;
          padding: 6px 8px;
          justify-content:space-between;
          color: var(--primary-text-color);
          background: inherit;  /* ← This makes header use card background */
          align-items:center;  /* This vertically centers everything */
          margin-bottom:2px;
          font-size:1.2em;
          font-weight:600
        }

        .scheme-cycle-button {
          --mdc-icon-button-size: 40px;
          --mdc-icon-size: 24px;
          background: rgba(var(--rgb-primary-color), 0.15);
          border-radius: 50%;
          backdrop-filter: blur(4px);
          padding: 8px 16px;
          border: none;
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 0.7em;  /* Make text smaller so button fits better */
        }

        .scheme-cycle-button:hover {
          background: rgba(var(--rgb-primary-color), 0.3);
        }
        .row1 {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 4px;
          width: 100%;
          line-height: 1;
          flex-shrink: 0;
          margin-top: -4px;
        }
        .vlan-dot {width:5px;height:5px;border-radius:50%;box-shadow:0 0 1px rgba(0,0,0,0.6);display:inline-block;transform:translateY(-1px)}
        .port-num{font-size:0.95em;font-weight:700}
        .port-direction{font-size:1.05em;margin-left:4px}
        .port-status{font-size:0.9em;margin-top:4px}
        .port-row {
          line-height: 1.1;
          opacity: 0.90;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          text-align: center;
          flex: 1;
          margin-top: -2px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .system-box {
          background: rgba(var(--rgb-card-background-color,255,255,255),0.08);
          backdrop-filter: blur(8px);
          padding: 3px 3px;
          margin-top: -10px;
          border-radius: 8px;
          text-align: center;
          box-shadow: 0 2px 6px rgba(0,0,0,0.12);
          cursor: pointer; /* ← Makes mouse show it's clickable */
          transition: all 0.2s ease; /* ← Smooth hover */
        }

        .system-box:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 10px rgba(0,0,0,0.2);
          background: rgba(var(--rgb-card-background-color,255,255,255),0.15);
        }
        /* Adjust spacing when row3 is hidden */
        .port.no-row3 .port-row {
          margin-top: 1px;
        }
        .port.no-row3 {
          justify-content: center;
        }
        .port.off{background:var(--disabled-background-color);opacity:0.95;color:var(--secondary-text-color);}
        .port.on-10g    { background: var(--switch-port-10g-color, #1e88e5); color: white; }
        .port.on-5g     { background: var(--switch-port-5g-color, #1565c0); color: white;}
        .port.on-2_5g   { background: var(--switch-port-2_5g-color, #1976d2); color: white;}
        .port.on-1g     { background: var(--switch-port-1g-color, #4caf50); color: white;}
        .port.on-100m   { background: var(--switch-port-100m-color, #ff9800); color: black;}
        .port.on-10m    { background: var(--switch-port-10m-color, #f44336); color: white;}
        .port.on-0m    { background: var(--switch-port-0m-color, #454444ff); color: white;}
        .port.sfp{border:2px solid #2196f3!important;border-radius: 1px;;box-shadow:0 0 12px rgba(33,150,243,.45)!important}

        .port.size-xsmall {
          font-size: 0.60em !important;
          padding-top: 6px !important;
        }
        .port.size-small {
          font-size: 0.80em !important;
          padding-top: 6px !important;
        }
        .port.size-medium {
          font-size: 1em !important;
          padding-top: 6px !important;
        }
        .port.size-large {
          font-size: 1.20em !important;
          padding-top: 6px !important;
        }
        .port.size-xlarge {
          font-size: 1.40em !important;
          padding-top: 6px !important;
        }
        .ports-staggered {
          display: flex;
          flex-direction: column;
          gap: 8px;  /* Space between top and bottom row */
        }

        .compact .ports-staggered {
          gap: 4px;
        }
        .compact .port.size-xlarge {
          font-size: 0.72em !important;
        }
        .compact .port.font-xlarge .port-num,
        .compact .port.font-xlarge .port-row { font-size: 0.68em !important; }

        .poe-indicator{position:absolute;top:4px;right:6px;font-size:0.7em;font-weight:bold;color:#00ff00;text-shadow:0 0 4px #000}

        .compact .port{aspect-ratio:3.6/1!important;font-size:0.58em!important;padding-top:4px}
        .compact .system-grid{gap:8px;margin:8px 0 4px 0}
        .compact .info-box{padding:5px 6px}

        @media (max-width: 900px) {
          .ports-grid {
            grid-template-columns: repeat(auto-fit, minmax(var(--port-min-width, 40px), 1fr));
          }
        }
        .top-row, .bottom-row {
          margin-bottom: 4px;  /* Space between top/bottom */
        }

        .compact .top-row, .compact .bottom-row {
          margin-bottom: 2px;
        }
        /* HEATMAP COLORS */
        .heatmap-10 { background: var(--switch-port-heat-10, #ff1744); color: white;}
        .heatmap-9  { background: var(--switch-port-heat-9, #ff5722); color: white;}
        .heatmap-8  { background: var(--switch-port-heat-8, #ff9800); color: black;}
        .heatmap-7  { background: var(--switch-port-heat-7, #ffc107); color: black;}
        .heatmap-6  { background: var(--switch-port-heat-6, #ffeb3b); color: black;}
        .heatmap-5  { background: var(--switch-port-heat-5, #cddc39); color: black;}
        .heatmap-4  { background: var(--switch-port-heat-4, #8bc34a); color: black;}
        .heatmap-3  { background: var(--switch-port-heat-3, #4caf50); color: black;}
        .heatmap-2  { background: var(--switch-port-heat-2, #2e7d32); color: white;}
        .heatmap-1  { background: var(--switch-port-heat-1, #1b5e20); color: white;}

        /* ACTUAL SPEED COLORS */
        .actual-100m { background: var(--switch-port-actual-high, #9c27b0); }
        .actual-10m  { background: var(--switch-port-actual-med, #4176ff); }
        .actual-1m  { background: var(--switch-port-actual-low, #23a9f4); color: black;} 
        .actual-100k { background: var(--switch-port-actual-low, #ffeb3b); color: black;}
        .actual-1k   { background: var(--switch-port-actual-low, #ffa800); color: black;}
        .actual-off  { background: var(--switch-port-actual-off, #191919); color: white;}

        /* VLAN MODE */
        .vlan-colored { transition: none; }

        ha-card {
          background: ${this._config.card_background_color 
            ? this._config.card_background_color 
            : 'var(--ha-card-background, var(--card-background-color))'};
          padding: 1px;
          border-radius: var(--ha-card-border-radius, 8px);
          box-shadow: none !important;
          border: none !important;
        }
      </style>
      <ha-card>
        <div class="header">
          <span id="title">Switch</span>
          <button class="scheme-cycle-button" id="scheme-button">${this._config.color_scheme}</button>
          <span id="bandwidth"></span>
        </div>
        <div class="gauge" id="gauge"><div class="gauge-fill" id="fill"></div></div>
        <div class="ports-section ${c}">
          <div class="section-label ${this._config.show_port_type_labels ? '' : 'section-hidden'}">COPPER</div>
          <div class="ports-grid" id="copper"></div>

          <div class="section-label ${this._config.show_port_type_labels ? '' : 'section-hidden'}">FIBER</div>
          <div class="ports-grid" id="sfp"></div>
        </div>
        <div class="system-grid ${c}" id="system"></div>
      </ha-card>
    `;

    this._applyPortsPerRow();
    this._applyPortsPerRowStaggered();
    const schemeButton = this.shadowRoot.getElementById("scheme-button");
    if (schemeButton) {
      schemeButton.addEventListener("click", () => this._cycleColorScheme());
    }
  }

  _formatLastSeen(seconds) {
    if (!seconds || seconds <= 0) return "—";
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h`;
    return "<1h";
  }

  _applyPortsPerRow() {
    if (!this.shadowRoot) return;

    const portsPerRow = this._config.ports_per_row || 8;
    const copperGrid = this.shadowRoot.getElementById("copper");
    const sfpGrid = this.shadowRoot.getElementById("sfp");

    if (copperGrid && sfpGrid) {
      const gridStyle = `repeat(${portsPerRow}, 1fr)`;
      copperGrid.style.gridTemplateColumns = gridStyle;
      sfpGrid.style.gridTemplateColumns = gridStyle;
    }
  }

  _vlanColor(vlan) {
    if (!vlan) return "transparent";
    const colors = [
      "#dc5d87ff", "#7b6291ff", "#7f798aff", "#434f94ff", "#57a5e4ff",
      "#015881ff", "#00bcd4", "#009688", "#4caf50", "#8bc34a",
      "#ffc107", "#ff9800", "#ff5722", "#795548", "#607d8b",
      "#4fc3f7", "#ba68c8", "#ffb74d", "#aed581", "#ce93d8"
    ];
    return colors[vlan % colors.length];
  }

  _formatTime(s) {
    if (!s) return "—";
    const h=Math.floor(s/3600),d=Math.floor(h/24);
    if(d>0)return`${d}d ${h%24}h`;
    if(h>0)return`${h}h ${Math.floor((s%3600)/60)}m`;
    return`${Math.floor(s/60)}m`;
  }

  _getContrastYIQ(hexcolor) {
    if (!hexcolor || hexcolor === "transparent") return 255;
    const rgb = hexcolor.match(/\w\w/g)?.map(x => parseInt(x, 16)) || [128,128,128];
    return (rgb[0]*299 + rgb[1]*587 + rgb[2]*114) / 1000;
  }

  _renderSystemInfo() {
  const show = this._config.system_boxes || {};
  const data = this._systemData || {};

  return html`
    <div class="system-tray">
      ${show.cpu ? html`
        <div class="system-box" @click=${() => this._showEntityDetails(this._entities.cpu?.entity_id)}>
          <span class="system-label">CPU</span>
          <span class="system-value">${data.cpu || '--'}</span>
        </div>` : ''}
      ${show.memory ? html`
        <div class="system-box" @click=${() => this._showEntityDetails(this._entities.memory?.entity_id)}>
          <span class="system-label">Memory</span>
          <span class="system-value">${data.memory || '--'}</span>
        </div>` : ''}
      ${show.firmware ? html`
        <div class="system-box" @click=${() => this._showEntityDetails(this._entities.firmware?.entity_id)}>
          <span class="system-label">Firmware</span>
          <span class="system-value">${data.firmware || '--'}</span>
        </div>` : ''}
      ${show.hostname ? html`
        <div class="system-box" @click=${() => this._showEntityDetails(this._entities.hostname?.entity_id)}>
          <span class="system-label">Hostname</span>
          <span class="system-value">${data.hostname || '--'}</span>
        </div>` : ''}
      ${show.uptime ? html`
        <div class="system-box" @click=${() => this._showEntityDetails(this._entities.uptime?.entity_id)}>
          <span class="system-label">Uptime</span>
          <span class="system-value">${data.uptime || '--'}</span>
        </div>` : ''}
      ${show.poe ? html`
        <div class="system-box" @click=${() => this._showEntityDetails(this._entities.total_poe?.entity_id)}>
          <span class="system-label">PoE Total</span>
          <span class="system-value">${data.total_poe || '--'}</span>
        </div>` : ''}
      ${show.custom ? html`
        <div class="system-box" @click=${() => this._showEntityDetails(this._entities.custom_value?.entity_id)}>
          <span class="system-label">${this._config.custom_text || 'Custom'}</span>
          <span class="system-value">${data.custom || '--'}</span>
        </div>` : ''}
    </div>`;
  }

  _showEntityDetails(entityId) {
    if (!entityId || !this._hass) return;

    // Dispatch HA's more-info event
    this.dispatchEvent(new CustomEvent('hass-more-info', {
      bubbles: true,
      composed: true,
      detail: { entityId }
    }));
  }

  _cycleColorScheme() {

    const schemes = ["speed", "heatmap", "vlan", "actual_speed"];
    const current = this._config.color_scheme || "speed";
    
    const currentIndex = schemes.indexOf(current);
    const nextIndex = (currentIndex === -1 ? 0 : currentIndex + 1) % schemes.length;
    const nextScheme = schemes[nextIndex];

    // Update config and trigger re-render
    const newConfig = {
      ...this._config,
      color_scheme: nextScheme
    };

    this._config = newConfig;  // Important: update local config

    // Fire config-changed event for editor persistence
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: newConfig },
      bubbles: true,
      composed: true
    }));

    // Force immediate re-render
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;

    this._applyPortsPerRow();
    // fix the button
    const schemeButton = this.shadowRoot.getElementById("scheme-button");
    if (schemeButton) {
      const schemeText = (this._config.color_scheme || "speed")
        .replace(/_/g, " ")
        .replace(/\b\w/g, l => l.toUpperCase());
      schemeButton.textContent = schemeText;
    }

    const e = this._entities || {};
    if (Object.keys(e).length===0) {
      this.shadowRoot.querySelector(".header").innerHTML = `<span style="color:var(--label-badge-red)">No data — check integration</span>`;
      return;
    }

    const bw=e.bandwidth, cpu=e.cpu, mem=e.memory, fw=e.firmware, up=e.uptime, host=e.hostname, poe=e.total_poe, customVal=e.custom_value;

    // Header + Bandwidth
    this.shadowRoot.getElementById("title").textContent = this._config.name || (host?.state?.trim()) || "Switch";
    let bwText = "— Mbps";
    if (bw?.state) {
      let val = Number(bw.state);
      const u = (bw.attributes?.unit_of_measurement || "").toLowerCase();
      let unit = "Mbps";  // default

      if (u.includes("gbit") || (u.includes("mbit") && val > 1000)) {
        val = val / 1000;
        unit = "Gbps";
      } else if (u.includes("bit/s") && !u.includes("mbit") && !u.includes("kbit") && !u.includes("gbit")) {
        val = val / 1e6;
      } else if (u.includes("kbit")) {
        val = val / 1e3;
      }

      bwText = `${val.toFixed(1)} ${unit}`;
    }
    this.shadowRoot.getElementById("bandwidth").textContent = bwText;

    // System boxes
    const sysCfg = this._config.system_boxes || {};
    if (this._config.show_system_info !== false) {
      const makeBox = (value, label) => {
        if (value == null || value === "unknown") return '';
        const isLong = value.toString().length > 10;
        return `<div class="info-box ${isLong ? 'firmware' : ''}">
          <div class="info-value">${value}</div>
          <div class="info-label">${label}</div>
        </div>`;
      };
      const getEntity = (overrideKey, fallbackEntity) => {
        const overrideId = this._config.system_box_overrides?.[overrideKey];
        if (overrideId && this._hass.states[overrideId]) {
          return this._hass.states[overrideId];
        }
        return fallbackEntity;
      };

      this.shadowRoot.getElementById("system").innerHTML = `
        ${sysCfg.cpu ? makeBox(getEntity("cpu", cpu)?.state != null ? Math.round(getEntity("cpu", cpu).state) + "%" : null, "CPU") : ""}
        ${sysCfg.memory ? makeBox(getEntity("memory", mem)?.state != null ? Math.round(getEntity("memory", mem).state) + "%" : null, "Memory") : ""}
        ${sysCfg.uptime ? makeBox(getEntity("uptime", up)?.state != null ? this._formatTime(Number(getEntity("uptime", up).state)) : null, "Up-time") : ""}
        ${sysCfg.hostname ? makeBox(getEntity("hostname", host)?.state, "Host") : ""}
        ${sysCfg.poe ? makeBox(getEntity("poe", poe)?.state != null ? getEntity("poe", poe).state + " W" : null, "PoE Total") : ""}
        ${sysCfg.firmware ? makeBox(getEntity("firmware", fw)?.state, "Firmware") : ""}
        ${sysCfg.custom ? makeBox(getEntity("custom", customVal)?.state, this._config.custom_text) : ""}
      `.trim();
    }
    else {
      this.shadowRoot.getElementById("system").innerHTML = ``;
    }
    
    // gauge
    const gauge = this.shadowRoot.getElementById("gauge");
    const fill = this.shadowRoot.getElementById("fill");
    if (this._config.show_total_bandwidth !== false && bw?.state) {
      gauge.style.display = "block";

      let val = Number(bw.state);
      const u = (bw.attributes?.unit_of_measurement || "").toLowerCase();
      let maxInMbps = (this._config.max_bandwidth_gbps || 100) * 1000;  // default max in Mbps

      if (u.includes("gbit") || (u.includes("mbit") && val > 1000)) {
        val = val / 1000;  // now in Gbps
        maxInMbps = this._config.max_bandwidth_gbps || 100;  // max is already in Gbps
      } else if (u.includes("bit/s") && !u.includes("mbit") && !u.includes("kbit") && !u.includes("gbit")) {
        val = val / 1e6;  // to Mbps
      } else if (u.includes("kbit")) {
        val = val / 1e3;  // to Mbps
      }

      const pct=Math.min((val/((this._config.max_bandwidth_gbps||100)*1000))*100,100);
      fill.style.width = `${pct}%`;
      fill.style.backgroundPosition = `${pct < 50 ? 0 : (pct - 50) * 2}% 0`;
    } else gauge.style.display="none";

    const formatTraffic = (bps) => {
      if (!bps || isNaN(bps) || bps === 0) return `0K`;
      const mbps = bps / 1e6;
      if (mbps >= 1000) return `${Math.round(mbps / 1000)}G`;
      if (mbps >= 1) return `${Math.round(mbps)}M`;
      return `${Math.round(bps / 1000)}K`;
    };

    const renderRowContent = (field, ctx, portIsOn) => {
      const key = (field || "").toLowerCase().trim();

      // Return null for "none" to skip rendering
      if (key === "none") return null;

      const truncate = (str, portSize = "medium") => {
        if (this._config.truncate_text !== true) {
          return str ?? '\u00A0';
        }

        if (!str) return '\u00A0';
        str = str.toString().trim();

        let maxChars;
        switch (portSize) {
          case "xsmall":   maxChars = 12; break;
          case "small":    maxChars = 11; break;
          case "medium":   maxChars = 10; break;
          case "large":    maxChars = 9;  break;
          case "xlarge":   maxChars = 7;  break;
          default:         maxChars = 10;
        }

        return str.length <= maxChars ? str : str.slice(0, maxChars - 2) + "..";
      };

      switch (key) {
        case "rx_tx_live":
        case "rx/tx_live":
        case "live":
          return `${formatTraffic(ctx.rxBps)}-${formatTraffic(ctx.txBps)}`;
        case "rx_tx":
        case "rx/tx":
        case "lifetime":
        case "total":
          return `${formatTraffic(ctx.rxBpsLifetime)}-${formatTraffic(ctx.txBpsLifetime)}`;
        case "speed":
          return portIsOn ? (ctx.speedText || '\u00A0') : '\u00A0';
        case "port_custom":
        case "custom":
          return truncate(ctx.port_custom, this._config.port_size || "small") || '\u00A0';
        case "name":
          return truncate(ctx.name, this._config.port_size || "small") || '\u00A0';
        case "interface":
          return truncate(ctx.ifDescr, this._config.port_size || "small") || '\u00A0';
        case "vlan_id":
        case "vlan":
          return ctx.vlan ? `VLAN ${ctx.vlan}` : '\u00A0';
        default:
          return '\u00A0';
      }
    };

    // PORTS
    const total = this._config.total_ports || 8;
    const sfpStart = this._config.sfp_start_port || 9;
    const copper = this.shadowRoot.getElementById("copper");
    const sfp = this.shadowRoot.getElementById("sfp");
    copper.innerHTML = "";
    sfp.innerHTML = "";

    const hasRow3 = this._config.row3 && this._config.row3.toLowerCase() !== "none";
    const now = Date.now() / 1000;
    const timeperiod = this._config.hide_unused_port_hours * 3600;

    // First pass: collect all ports and calculate max traffic for heatmap
    const allPorts = [];
    for (let i = 1; i <= total; i++) {
      const ent = e[`port_${i}_status`];
      if (!ent) continue;

      const rx = parseFloat(ent.attributes?.rx_bps_live || 0) || 0;
      const tx = parseFloat(ent.attributes?.tx_bps_live || 0) || 0;
      const vlan = ent.attributes?.vlan_id;

      allPorts.push({ i, traffic: rx + tx, vlan, ent });
    }

    const maxTraffic = Math.max(...allPorts.map(p => p.traffic), 1);

    // Second pass: filter and render only visible ports
    const visiblePorts = [];
    for (const port of allPorts) {
      const { i, ent } = port;
      const isOn = ent.state === "on";
      const lastChanged = new Date(ent.last_changed || ent.last_updated).getTime() / 1000;
      const idleSeconds = now - lastChanged;

      if (!isOn && this._config.hide_unused_port && idleSeconds >= timeperiod) {
        continue; // hide unused
      }

      visiblePorts.push({ ...port, isOn });
    }

    // Separate copper and SFP
    let copperPorts = visiblePorts.filter(p => p.i < sfpStart);
    let sfpPorts = visiblePorts.filter(p => p.i >= sfpStart);

    const layout = this._config.layout_mode || "linear";

    const rearrange = (ports) => {
      if (layout === "linear") {
        return { single: ports.sort((a, b) => a.i - b.i) };
      }

      const even = ports.filter(p => p.i % 2 === 0).sort((a, b) => a.i - b.i);
      const odd = ports.filter(p => p.i % 2 !== 0).sort((a, b) => a.i - b.i);

      if (layout === "even_top") {
        return { top: even, bottom: odd };
      } else {
        return { top: odd, bottom: even };
      }
    };

    const copperLayout = rearrange(copperPorts);
    const sfpLayout = rearrange(sfpPorts);

    const renderPortRow = (portList, container) => {
      portList.forEach(({ i, ent, isOn, traffic }) => {
        const speedMbps = Math.round((ent.attributes?.speed_bps || 0) / 1e6) || 0;
        const name = ent.attributes?.port_name?.trim() || `Port ${i}`;
        const vlan = ent.attributes?.vlan_id;
        const poeEnabled = ent.attributes?.poe_enabled === true;
        const ifDescr = ent.attributes?.interface || "";
        const port_custom = ent.attributes?.custom || "";

        const rxBps = parseFloat(ent.attributes?.rx_bps_live || 0) || 0;
        const txBps = parseFloat(ent.attributes?.tx_bps_live || 0) || 0;
        const rxBpsLifetime = parseInt(ent.attributes?.rx_bps || 0) || 0;
        const txBpsLifetime = parseInt(ent.attributes?.tx_bps || 0) || 0;
        const lastChanged = new Date(ent.last_changed || ent.last_updated).getTime() / 1000;
        const idleSeconds = now - lastChanged;

        let speedClass = "off";
        let speedText = "OFF";
        let direction = "";

        if (isOn) {
          const totalBps = rxBps + txBps;

          switch (this._config.color_scheme || "speed") {
            case "speed":
              if (speedMbps >= 10000) { speedClass = "on-10g"; speedText = "10G"; }
              else if (speedMbps >= 5000) { speedClass = "on-5g"; speedText = "5G"; }
              else if (speedMbps >= 2500) { speedClass = "on-2_5g"; speedText = "2.5G"; }
              else if (speedMbps >= 1000) { speedClass = "on-1g"; speedText = "1G"; }
              else if (speedMbps >= 100) { speedClass = "on-100m"; speedText = "100M"; }
              else if (speedMbps >= 10) { speedClass = "on-10m"; speedText = "10M"; }
              else { speedClass = "on-0m"; speedText = `${speedMbps}M`; }
              break;

            case "heatmap":
              const ratio = maxTraffic > 0 ? traffic / maxTraffic : 0;
              if (ratio > 0.9) speedClass = "heatmap-10";
              else if (ratio > 0.8) speedClass = "heatmap-9";
              else if (ratio > 0.7) speedClass = "heatmap-8";
              else if (ratio > 0.6) speedClass = "heatmap-7";
              else if (ratio > 0.5) speedClass = "heatmap-6";
              else if (ratio > 0.4) speedClass = "heatmap-5";
              else if (ratio > 0.3) speedClass = "heatmap-4";
              else if (ratio > 0.2) speedClass = "heatmap-3";
              else if (ratio > 0.1) speedClass = "heatmap-2";
              else speedClass = "heatmap-1";
              speedText = formatTraffic(traffic);
              break;

            case "vlan":
              speedClass = "vlan-colored";
              break;

            case "actual_speed":
              const mbps = totalBps / 1e6;
              if (mbps >= 100) { speedClass = "actual-100m"; speedText = `${(mbps/1000).toFixed(1)}G`; }
              else if (mbps >= 10) { speedClass = "actual-10m"; speedText = `${mbps.toFixed(1)}M`; }
              else if (mbps >= 1) { speedClass = "actual-1m"; speedText = `${mbps.toFixed(0)}M`; }
              else if (mbps >= 0.1) { speedClass = "actual-100k"; speedText = `${(mbps*10).toFixed(0)}K`; }
              else if (mbps > 0.001) { speedClass = "actual-1k"; speedText = `${(mbps*100).toFixed(0)}K`; }
              else { speedClass = "actual-off"; speedText = "0k"; }
              break;

            default:
              speedClass = "on-1g";
          }

          if (rxBps > txBps * 1.8) direction = "\u2193";
          else if (txBps > rxBps * 1.8) direction = "\u2191";
          else direction = "\u2195";
        } else {
          speedText = "-";
          direction = "-";
        }

        const div = document.createElement("div");
        div.className = `port ${speedClass} ${i >= sfpStart ? "sfp" : ""} ${!isOn ? "off" : ""}`;
        const size = this._config.port_size || "medium";
        div.classList.add(`size-${size}`);
        div.style.cursor = "pointer";

        // VLAN coloring override
        if (this._config.color_scheme === "vlan") {
          const bg = vlan ? this._vlanColor(vlan) : "#607d8b";
          const textColor = this._getContrastYIQ(bg) < 128 ? "white" : "black";
          div.style.background = bg;
          div.style.color = textColor;
          div.style.border = "1px solid rgba(255,255,255,0.15)";
        }

        const balancedGlyph = "\u2195";
        const portDirectionDisplay = isOn
          ? (direction === "\u2193" || direction === "\u2191" ? direction : balancedGlyph)
          : "-";

        const ctx = {
          rxBpsLifetime,
          txBpsLifetime,
          rxBps,
          txBps,
          speedText,
          port_custom,
          name,
          ifDescr,
          vlan
        };

        const row2Content = renderRowContent(this._config.row2, ctx, isOn);
        const row3Content = renderRowContent(this._config.row3, ctx, isOn);
        const lastSeen = `Last seen: ${this._formatLastSeen(idleSeconds)}`;

        div.title =
          `${name}` +
          (ifDescr ? `\nInterface: ${ifDescr}` : "") +
          `\nState: ${isOn ? "UP" : "DOWN"}` +
          `\nSpeed: ${speedText}` +
          (vlan ? `\nVLAN: ${vlan}` : "") +
          `\nRX: ${(rxBps / 1e6).toFixed(2)} Mb/s` +
          `\nTX: ${(txBps / 1e6).toFixed(2)} Mb/s` +
          (port_custom ? `\n${this._config.custom_port_text}: ${port_custom}` : "") +
          `\n${lastSeen}`;

        div.onclick = (ev) => {
          ev.stopPropagation();
          const entityId = this._entities[`port_${i}_status`]?.entity_id;
          this._showEntityDetails(entityId);
        };

        div.classList.toggle("no-row3", !hasRow3);

        div.innerHTML = `
          <div class="row1">
            <span class="vlan-dot" style="background:${this._vlanColor(vlan)}"></span>
            <span class="port-num">${i}</span>
            <span class="port-direction">${portDirectionDisplay}</span>
          </div>

          ${row2Content !== null ? `<div class="port-row">${row2Content}</div>` : ``}

          ${hasRow3 && row3Content !== null ? `<div class="port-row">${row3Content}</div>` : ``}

          ${poeEnabled ? '<div class="poe-indicator">P</div>' : ''}
        `;

        container.appendChild(div);
      });
    };

    // Render Copper
    if (layout === "linear") {
      renderPortRow(copperLayout.single || [], copper);
      copper.classList.remove("ports-staggered");
      copper.style.gridTemplateColumns = `repeat(${this._config.ports_per_row || 8}, 1fr)`;
    } else {
      copper.classList.add("ports-staggered");  // Add class to parent
      copper.style.gridTemplateColumns = "none";  // Remove grid from parent
      copper.innerHTML = `
        <div class="ports-grid top-row"></div>
        <div class="ports-grid bottom-row"></div>
      `;
      const topRow = copper.querySelector(".top-row");
      const bottomRow = copper.querySelector(".bottom-row");
      this._applyPortsPerRowToGrid(topRow);
      this._applyPortsPerRowToGrid(bottomRow);

      renderPortRow(copperLayout.top || [], topRow);
      renderPortRow(copperLayout.bottom || [], bottomRow);
    }

// Render SFP — always linear, ignore layout_mode
    renderPortRow(sfpPorts.sort((a, b) => a.i - b.i), sfp);
  }

  getCardSize() { return this._config.compact_mode ? 5 : 8; }
}



class SwitchPortCardProEditor extends HTMLElement {
  setConfig(config) {
    // Merge the user's config with the master defaults.
    // This ensures 'system_boxes' and other nested objects always exist.
    this._config = {
      ...DEFAULT_CONFIG,
      ...config,
      // Ensure nested objects are also merged correctly if the user has a partial config
      system_boxes: {
        ...DEFAULT_CONFIG.system_boxes,
        ...(config?.system_boxes || {})
      }
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!hass || this._last === JSON.stringify(this._config)) return;
  // Prevent infinite re-rendering loop
    const configStr = JSON.stringify(this._config);
    if (this._last === configStr) return;
    this._last = configStr;

    const seen = new Set();
    const deviceList = [];

    Object.values(hass.states).forEach(entity => {
      if (entity.entity_id.includes("_total_bandwidth")) {
        const friendly = entity.attributes?.friendly_name || entity.entity_id;
        const name = friendly.replace(/ Total Bandwidth.*/i, '').trim();
        if (name && !seen.has(name)) {
          seen.add(name);
          const prefix = entity.entity_id.split("_total_bandwidth")[0]; // e.g. "sensor.xgs1935"
          deviceList.push({ id: prefix, name });
        }
      }
    });

    deviceList.sort((a,b) => a.name.localeCompare(b.name));
    const entityList = Object.keys(hass.states).filter(e=>e.includes("_port_")||e.includes("_bandwidth")||e.includes("_total_poe")).sort();

    // Options for rows
    const rowOptions = [
      { val: "none",       label: "Hidden (hide row)" },
      { val: "rx_tx_live", label: "Live RX/TX (Mbps)" },
      { val: "rx_tx",      label: "Lifetime RX/TX" },
      { val: "speed",      label: "Speed" },
      { val: "port_custom", label: "Custom Port Value" },
      { val: "name",       label: "Port Name" },
      { val: "interface",  label: "Interface" },
      { val: "vlan_id",    label: "VLAN ID" }
    ];

    const makeOptions = (selected) => rowOptions.map(o => `<option value="${o.val}" ${o.val===selected?'selected':''}>${o.label}</option>`).join('');

    this.innerHTML = `
      <style>
        .row{margin:14px 0;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
        label{min-width:160px;font-weight:500;color:var(--primary-text-color)}
        select,input{flex:1;padding:8px;border-radius:6px;border:1px solid var(--divider-color);background:var(--input-background-color,#444);color:var(--input-text-color,#fff)}
        .checkbox-row{display:flex;align-items:center;gap:16px;margin:10px 0}
        .checkbox-label{font-weight:500;color:var(--primary-text-color);cursor:pointer}
        .row{margin:14px 0;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
        label{min-width:160px;font-weight:500;color:var(--primary-text-color)}
        select,input{flex:1;padding:8px;border-radius:6px;border:1px solid var(--divider-color);background:var(--input-background-color,#444);color:var(--input-text-color,#fff)}
        .checkbox-row{display:flex;align-items:center;gap:4px;margin:2px 0}
        .checkbox-label{font-weight:500;color:var(--primary-text-color);cursor:pointer}

        /* NEW: Grid layouts for compact fields */
        .row-group {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 2px;
          margin: 2px 0;
        }
        .row-group-2 {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 2px;
          margin: 2px 0;
        }
        .field {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .field label {
          min-width: unset;
          font-size: 0.85em;
          margin-bottom: 0px;
        }
        .field input, .field select {
          width: 87%;
        }
      </style>
      <div style="padding:16px">
        <div class="row"><label>Title</label><input type="text" data-key="name" value="${this._config.name||''}"></div>
        <div class="row"><label>Device</label>
          <select data-key="device">
            <option value="">-- Select switch --</option>
            ${deviceList.map(d=>`<option value="${d.id}" ${d.id===this._config.device?'selected':''}>${d.name}</option>`).join('')}
          </select>
        </div>
        <div class="row-group">
            <div class="field"><label>Total Ports</label><input type="number" data-key="total_ports" value="${this._config.total_ports||8}"></div>
            <div class="field"><label>First SFP Port</label><input type="number" data-key="sfp_start_port" value="${this._config.sfp_start_port||9}"></div>
            <div class="field"><label>Bandwidth(Gbps)</label><input type="number" step="10" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps || 100}"></div>
        </div>
        <div class="row-group-2">
          <div class="field"><label>Custom system value text</label><input type="text" data-key="custom_text" value="${this._config.custom_text||'Custom'}"></div>
          <div class="field"><label>Custom port value text</label><input type="text" data-key="custom_port_text" value="${this._config.custom_port_text || 'Custom Port'}"></div>
        </div>
        <div class="row-group-2">
          <div class="field">
            <label>Port Size</label>
            <select data-key="port_size">
                <option value="xsmall"   ${this._config.port_size === "xsmall"   ? "selected" : ""}>Extra Small</option>
                <option value="small"   ${this._config.port_size === "small"   ? "selected" : ""}>Small</option>
                <option value="medium"  ${this._config.port_size === "medium"  ? "selected" : ""}>Medium (default)</option>
                <option value="large"   ${this._config.port_size === "large"   ? "selected" : ""}>Large</option>
                <option value="xlarge"  ${this._config.port_size === "xlarge"  ? "selected" : ""}>Extra Large</option>
            </select>
          </div>
          <div class="field">
            <label>Ports Per Row</label>
            <input type="number" min="1" max="24" data-key="ports_per_row" value="${this._config.ports_per_row || 8}">
          </div>
        </div>
        <div class="row">
          <label>Port Layout</label>
          <select data-key="layout_mode">
            <option value="linear" ${this._config.layout_mode === "linear" ? "selected" : ""}>Linear (single row)</option>
            <option value="even_top" ${this._config.layout_mode === "even_top" ? "selected" : ""}>Staggered (Even on top)</option>
            <option value="odd_top" ${this._config.layout_mode === "odd_top" ? "selected" : ""}>Staggered (Odd on top)</option>
          </select>
        </div>
        <div class="row"><label>Port row 2 display</label>
          <select data-key="row2">
            ${makeOptions(this._config.row2)}
          </select>
        </div>
        <div class="row"><label>Port row 3 display </label>
          <select data-key="row3">
            ${makeOptions(this._config.row3)}
          </select>
        </div>
        <div class="row">
          <label>Port Color Scheme</label>
          <select data-key="color_scheme">
            <option value="speed" ${this._config.color_scheme === "speed" ? "selected" : ""}>Link Speed</option>
            <option value="heatmap" ${this._config.color_scheme === "heatmap" ? "selected" : ""}>Heatmap (Traffic)</option>
            <option value="vlan" ${this._config.color_scheme === "vlan" ? "selected" : ""}>VLAN Colored</option>
            <option value="actual_speed" ${this._config.color_scheme === "actual_speed" ? "selected" : ""}>Actual Speed</option>
          </select>
        </div>
        <div class="row">
          <label>Card Background Color</label>
          <input
            type="text"
            data-key="card_background_color"
            placeholder="rgba(23, 22, 22, 0.4)"
            value="${this._config.card_background_color || ''}">
        </div>
        <div class="checkbox-row">
          <ha-checkbox data-key="show_total_bandwidth" ${this._config.show_total_bandwidth!==false ? 'checked':''}></ha-checkbox>
          <span class="checkbox-label">Show Bandwidth Gauge</span>
        </div>

        <!-- Show System Info Switch -->
        <div class="checkbox-row">
          <ha-checkbox data-key="show_system_info" ${this._config.show_system_info !== false ? 'checked' : ''}></ha-checkbox>
          <span class="checkbox-label">Show System Info (CPU, Mem, FW, etc.)</span>
        </div>

        <div class="row-group">
          <div class="checkbox-row">
            <ha-checkbox data-key="system_boxes.cpu" ${this._config.system_boxes.cpu !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">CPU</span>
          </div>
          <div class="checkbox-row">
            <ha-checkbox data-key="system_boxes.memory" ${this._config.system_boxes.memory !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Memory</span>
          </div>
          <div class="checkbox-row">
            <ha-checkbox data-key="system_boxes.uptime" ${this._config.system_boxes.uptime !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Uptime</span>
          </div>
          <div class="checkbox-row">
            <ha-checkbox data-key="system_boxes.hostname" ${this._config.system_boxes.hostname !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Host</span>
          </div>
          <div class="checkbox-row">
            <ha-checkbox data-key="system_boxes.poe" ${this._config.system_boxes.poe !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">PoE</span>
          </div>
          <div class="checkbox-row">
            <ha-checkbox data-key="system_boxes.firmware" ${this._config.system_boxes.firmware !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Firmware</span>
          </div>
          <div class="checkbox-row">
            <ha-checkbox data-key="system_boxes.custom" ${this._config.system_boxes.custom !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Custom</span>
          </div>
        </div>
        <!-- System Box Overrides (type entity ID manually) -->
        <div class="row">
          <label>System Box Overrides (optional - type entity ID, leave blank for auto)</label>
        </div>
        <div class="row-group">
          <div class="field"><label>CPU Override</label>
            <input type="text" placeholder="e.g. sensor.switch_cpu" data-key="system_box_overrides.cpu" value="${this._config.system_box_overrides?.cpu || ''}">
          </div>
          <div class="field"><label>Memory Override</label>
            <input type="text" placeholder="e.g. sensor.switch_memory" data-key="system_box_overrides.memory" value="${this._config.system_box_overrides?.memory || ''}">
          </div>
          <div class="field"><label>Uptime Override</label>
            <input type="text" placeholder="e.g. sensor.switch_uptime" data-key="system_box_overrides.uptime" value="${this._config.system_box_overrides?.uptime || ''}">
          </div>
          <div class="field"><label>Hostname Override</label>
            <input type="text" placeholder="e.g. sensor.switch_hostname" data-key="system_box_overrides.hostname" value="${this._config.system_box_overrides?.hostname || ''}">
          </div>
          <div class="field"><label>PoE Override</label>
            <input type="text" placeholder="e.g. sensor.switch_poe" data-key="system_box_overrides.poe" value="${this._config.system_box_overrides?.poe || ''}">
          </div>
          <div class="field"><label>Firmware Override</label>
            <input type="text" placeholder="e.g. sensor.switch_firmware" data-key="system_box_overrides.firmware" value="${this._config.system_box_overrides?.firmware || ''}">
          </div>
          <div class="field"><label>Custom Override</label>
            <input type="text" placeholder="e.g. sensor.my_custom" data-key="system_box_overrides.custom" value="${this._config.system_box_overrides?.custom || ''}">
          </div>
        </div>

        <div class="checkbox-row">
          <ha-checkbox data-key="show_port_type_labels" ${this._config.show_port_type_labels !== false ? 'checked' : ''}></ha-checkbox>
          <span class="checkbox-label">Show Port Section Title (Copper/Fiber)</span>
        </div>
        <div class="checkbox-row">
          <ha-checkbox data-key="hide_unused_port" ${this._config.hide_unused_port ? 'checked' : ''}></ha-checkbox>
          <span class="checkbox-label">Hide Unused Ports</span>
          <span class="field"><label>inactive for (>hours)</span><input type="text" data-key="hide_unused_port_hours" value="${this._config.hide_unused_port_hours || 0}">
        </div>
      </div>
    `;

    const setDeep = (obj, path, value) => {
      const keys = path.split(".");
      const last = keys.pop();
      const target = keys.reduce((o, k) => (o[k] ??= {}), obj);
      target[last] = value;
    };

    this.querySelectorAll("[data-key]").forEach(el => {
      el.addEventListener("change", () => {
        const key = el.dataset.key;
        const value = el.tagName === "HA-CHECKBOX" ? el.checked : el.value;

        const newConfig = structuredClone(this._config);
        setDeep(newConfig, key, value);

        this._config = newConfig;
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

(function () {
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "switch-port-card-pro",
    name: "Switch Port Card Pro",
    description: "Visualize switch ports", 
    preview: true,
  });
})();
