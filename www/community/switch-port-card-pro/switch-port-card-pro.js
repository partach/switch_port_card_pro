// switch-port-card-pro.js
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
      total_ports: 8,
      sfp_start_port: 9,
      custom_text: "Custom Value",
      custom_port_text: "Custom Port Val.",
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      compact_mode: false,
      show_system_info: true,
      show_port_type_labels: true,
      // Row configuration defaults
      row2: "rx_tx_live",
      row3: "speed",
    };
  }

  setConfig(config) {
    this._config = {
      name: "Network Switch",
      total_ports: 8,
      sfp_start_port: 9,
      custom_text: "Custom Value",
      custom_port_text: "Custom Port Val.",
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      compact_mode: false,
      show_system_info: true,
      show_port_type_labels: true,
      row2: "rx_tx_live",
      row3: "speed",
      ...config
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) this._config = { total_ports:8, sfp_start_port:9, show_total_bandwidth:true, max_bandwidth_gbps:100, compact_mode:false };
    if (!this._entities || this._lastHass !== hass) {
      this._entities = this._collectEntities(hass);
      this._lastHass = hass;
    }
    if (!this.shadowRoot.querySelector("ha-card")) this._createSkeleton();
    this._render();
  }

  _collectEntities(hass) {
    const entities = {};
    if (!this._config) return entities;

    let searchEntities = [];

    // CASE 1: User selected a switch from the "Switch (auto)" dropdown → it's a PREFIX, not a device_id
    if (this._config.device) {
      const prefix = this._config.device.endsWith('_') ? this._config.device : this._config.device + "_";
      searchEntities = Object.keys(hass.states).filter(id => id.startsWith(prefix));
    }

    // CASE 2: No device selected → use fallback entity prefix (your old reliable way)
    if (searchEntities.length === 0 && this._config.entity) {
      const parts = this._config.entity.split("_total_bandwidth");
      if (parts.length > 1) {
        const prefix = parts[0] + "_";
        searchEntities = Object.keys(hass.states).filter(id => id.startsWith(prefix));
      } else {
        // Single entity fallback (very rare)
        searchEntities = [this._config.entity];
      }
    }

    // CASE 3: Still nothing? → search everything (should never happen)
    if (searchEntities.length === 0) {
      searchEntities = Object.keys(hass.states);
    }

    // Now scan the final list exactly like before
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

  _createSkeleton() {
    const c = this._config.compact_mode ? "compact" : "";
    this.shadowRoot.innerHTML = `
      <style>
        .section-hidden {
          display: none !important;
        }
        .section-hidden + .ports-grid {
          margin-top: 8px;
        }
        :host{display:block;background:var(--ha-card-background,var(--card-background-color,#fff));color:var(--primary-text-color);padding:7px;border-radius:var(--ha-card-border-radius,12px);font-family:var(--ha-font-family,Roboto)}
        .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:1.2em;font-weight:600}
        .system-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:12px;margin:20px 0 8px 0}
        .info-box{background:rgba(var(--rgb-card-background-color,255,255,255),0.08);backdrop-filter:blur(8px);padding:7px 9px;border-radius:10px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.12)}
        .info-value{font-size:1.05em;font-weight:bold;line-height:1.05;margin:0}
        .info-label{font-size:0.8em;opacity:0.8;color:var(--secondary-text-color);line-height:1.2;margin-top:1px}
        .info-box.firmware .info-value{font-size:0.6em!important;font-weight:normal!important;line-height:1.3}
        .gauge{height:18px;background:var(--light-primary-color);border-radius:12px;overflow:hidden;margin:16px 0;display:none;position:relative}
        .gauge-fill{height:100%;background:linear-gradient(90deg,var(--label-badge-green,#4caf50),var(--label-badge-yellow,#ff9800) 50%,var(--label-badge-red,#f44336));background-size:300% 100%;width:100%;transition:background-position .8s ease}
        .section-label{font-size:0.9em;font-weight:600;color:var(--secondary-text-color);margin:8px 0 4px;text-align:center;width:100%}
        .ports-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(${c?'40px':'50px'},1fr));gap:6px}
        .port{aspect-ratio:2.6/1;background:var(--light-primary-color);border-radius:8px;display:flex;flex-direction:column;justify-content:flex-start;align-items:center;font-weight:bold;font-size:0.80em;cursor:default;transition:all .15s;position:relative;box-shadow:0 1px 3px rgba(0,0,0,.2),inset 0 1px 0 rgba(255,255,255,.06);padding-top:6px}
        .port:hover{transform:scale(1.06);z-index:10}
        /* Row-1 group */
        .row1{display:flex;align-items:center;gap:6px;justify-content:center;width:100%;font-size:0.95em;line-height:1}
        .vlan-dot {width:5px;height:5px;border-radius:50%;box-shadow:0 0 1px rgba(0,0,0,0.6);display:inline-block;transform:translateY(-1px)}
        .port-num{font-size:0.95em;font-weight:700}
        .port-direction{font-size:1.05em;margin-left:4px}
        .port-status{font-size:0.9em;margin-top:4px}
        .port-row{font-size:0.60em;line-height:1;opacity:0.95;margin-top:6px;min-height:1.15em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .port.off{background:var(--disabled-background-color);opacity:0.95;color:var(--secondary-text-color)}
        .port.on-10g{background:#1e88e5;color:white}
        .port.on-5g{background:#1565c0;color:white}
        .port.on-2_5g{background:#1976d2;color:white}
        .port.on-1g{background:#4caf50;color:white}
        .port.on-100m{background:#ff9800;color:black}
        .port.on-10m{background:#f44336;color:white}
        .port.sfp{border:2px solid #2196f3!important;box-shadow:0 0 12px rgba(33,150,243,.45)!important}
        .poe-indicator{position:absolute;top:4px;right:6px;font-size:0.7em;font-weight:bold;color:#00ff00;text-shadow:0 0 4px #000}
        .compact .ports-grid{grid-template-columns:repeat(auto-fit,minmax(40px,1fr))}
        .compact .port{aspect-ratio:3.6/1!important;font-size:0.58em!important;padding-top:4px}
        .compact .system-grid{gap:8px;margin:8px 0 4px 0}
        .compact .info-box{padding:5px 6px}
        @media(max-width:600px){.ports-grid{grid-template-columns:repeat(auto-fit,minmax(40px,1fr))}}
      </style>
      <ha-card>
        <div class="header"><span id="title">Switch</span><span id="bandwidth">— Mbps</span></div>
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
  }

  _vlanColor(vlan) {
    if (!vlan) return "transparent";

    // 20 distinct colors – consistent per VLAN
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

  _render() {
    if (!this._hass || !this._config) return;
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
      const u = (bw.attributes?.unit_of_measurement||"").toLowerCase();

      // SNMP integration bug: labels as Mbit/s but actually reports Kbps
      if (u.includes("mbit") && val > 1000) {
        val = val / 1000; // Convert Kbps to Mbps
      } else if (u.includes("bit/s") && !u.includes("mbit") && !u.includes("kbit") && !u.includes("gbit")) {
        val = val / 1e6; // bps to Mbps
      } else if (u.includes("kbit")) {
        val = val / 1e3; // Kbps to Mbps
      } else if (u.includes("gbit")) {
        val = val * 1e3; // Gbps to Mbps
      }
      bwText = `${val.toFixed(1)} Mbps`;
    }
    this.shadowRoot.getElementById("bandwidth").textContent = bwText;

    // System boxes
    if (this._config.show_system_info === true) {
      const makeBox = (value, label) => {
        if (value == null || value === "unknown") return '';
        const isLong = value.toString().length > 10;
        return `<div class="info-box ${isLong ? 'firmware' : ''}">
          <div class="info-value">${value}</div>
          <div class="info-label">${label}</div>
        </div>`;
      };

      this.shadowRoot.getElementById("system").innerHTML = `
        ${makeBox(cpu?.state != null ? Math.round(cpu.state) + "%" : null, "CPU")}
        ${makeBox(mem?.state != null ? Math.round(mem.state) + "%" : null, "Memory")}
        ${makeBox(up?.state != null ? this._formatTime(Number(up.state)) : null, "Uptime")}
        ${makeBox(host?.state, "Host")}
        ${makeBox(poe?.state != null ? poe.state + " W" : null, "PoE Total")}
        ${makeBox(fw?.state, "Firmware")}
        ${makeBox(customVal?.state, this._config.custom_text)}
      `.trim();
    }
    else {
      this.shadowRoot.getElementById("system").innerHTML = ``;
    }

    // Gauge
    const gauge=this.shadowRoot.getElementById("gauge"), fill=this.shadowRoot.getElementById("fill");
    if (this._config.show_total_bandwidth!==false && bw?.state) {
      gauge.style.display="block";
      let val=Number(bw.state);
      const u=(bw.attributes?.unit_of_measurement||"").toLowerCase();

      if (u.includes("mbit") && val > 1000) {
        val = val / 1000;
      } else if (u.includes("bit/s") && !u.includes("mbit") && !u.includes("kbit") && !u.includes("gbit")) {
        val = val / 1e6;
      } else if (u.includes("kbit")) {
        val = val / 1e3;
      } else if (u.includes("gbit")) {
        val = val * 1e3;
      }

      const pct=Math.min((val/((this._config.max_bandwidth_gbps||100)*1000))*100,100);
      fill.style.width = `${pct}%`;
      fill.style.backgroundPosition = `${pct < 50 ? 0 : (pct - 50) * 2}% 0`;
    } else gauge.style.display="none";

    // Helper: format traffic with proper units (Option C chosen: show 0 as 0K)
    const formatTraffic = (bps) => {
      if (!bps || isNaN(bps) || bps === 0) return `0K`;
      const mbps = bps / 1e6;
      if (mbps >= 1000) return `${(mbps/1000).toFixed(1)}G`;
      if (mbps >= 1) return `${mbps.toFixed(1)}M`;
      return `${(bps/1e3).toFixed(0)}K`;
    };

    // Helper to render row content based on config key
    const renderRowContent = (field, ctx, portIsOn) => {
      const key = (field || "").toLowerCase().trim();

      const truncate = (str, max = 12) => {
        if (!str) return '\u00A0';
        str = str.toString().trim();
        return str.length <= max ? str : str.slice(0, 10) + "..";
      };

      switch (key) {
        // LIVE TRAFFIC
        case "rx_tx_live":
        case "rx/tx_live":
        case "live":
          return `\u2193${formatTraffic(ctx.rxBps)} \u2191${formatTraffic(ctx.txBps)}`;

        // LIFETIME TRAFFIC
        case "rx_tx":
        case "rx/tx":
        case "lifetime":
        case "total":
          return `\u2193${formatTraffic(ctx.rxBpsLifetime)} \u2191${formatTraffic(ctx.txBpsLifetime)}`;

        case "speed":
          return portIsOn ? (ctx.speedText || '\u00A0') : '\u00A0';

        case "port_custom":
        case "custom":
          return truncate(ctx.port_custom) || '\u00A0';

        case "name":
          return truncate(ctx.name) || '\u00A0';

        case "interface":
          return truncate(ctx.ifDescr) || '\u00A0';

        case "vlan_id":
        case "vlan":
          return ctx.vlan ? `VLAN ${ctx.vlan}` : '\u00A0';

        default:
          return '\u00A0';
      }
    };

    // PORTS
    const total=this._config.total_ports||8;
    const sfpStart=this._config.sfp_start_port||9;
    const copper=this.shadowRoot.getElementById("copper");
    const sfp=this.shadowRoot.getElementById("sfp");
    copper.innerHTML=""; sfp.innerHTML="";

    for (let i=1;i<=total;i++) {
      const ent = e[`port_${i}_status`];
      if (!ent) continue;

      const isOn = ent.state==="on";
      const speedMbps = Math.round((ent.attributes?.speed_bps || 0) / 1e6) || 0;
      const name = ent.attributes?.port_name?.trim() || `Port ${i}`;
      const vlan = ent.attributes?.vlan_id;
      const poeEnabled = ent.attributes?.poe_enabled===true;
      const ifDescr = ent.attributes?.interface || "";
      const port_custom = ent.attributes?.custom || "";

      // Safe attribute reading

      const rxBps = parseFloat(ent.attributes?.rx_bps_live || 0) || 0;
      const txBps = parseFloat(ent.attributes?.tx_bps_live || 0) || 0;

      // Lifetime traffic — kept for backward compatibility
      const rxBpsLifetime = parseInt(ent.attributes?.rx_bps || 0) || 0;
      const txBpsLifetime = parseInt(ent.attributes?.tx_bps || 0) || 0;


      // Speed class & text
      let speedClass="off", speedText="OFF", direction="";
      if (isOn && speedMbps>0) {
        if (speedMbps>=10000){speedClass="on-10g";speedText="10G"}
        else if(speedMbps>=5000){speedClass="on-5g";speedText="5G"}
        else if(speedMbps>=2500){speedClass="on-2_5g";speedText="2.5G"}
        else if(speedMbps>=1000){speedClass="on-1g";speedText="1G"}
        else if(speedMbps>=100){speedClass="on-100m";speedText="100M"}
        else if(speedMbps>=10){speedClass="on-10m";speedText="10M"}
        else speedText=`${speedMbps}M`;

        if (rxBps > txBps*1.8) direction="\u2193";
        else if (txBps > rxBps*1.8) direction="\u2191";
        else direction = '\u2195'; // balanced indicator; we will show ↕ glyph (use \u2195 or \u21C5; using \u2195)
      } else {
        // Port OFF
        speedText = "-";
        direction = "-";
      }

      // Use the chosen balanced glyph (we want ↕ — use unicode U+2195 as visual up-down)
      const balancedGlyph = '\u2195'; // ↕

      const portDirectionDisplay = (() => {
        if (!isOn) return "-";
        if (direction === '\u2193' || direction === '\u2191') return direction;
        // balanced
        return balancedGlyph;
      })();

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

      // Row 1 display: must be fixed order - vlan-dot, port number, direction (arrow or OFF)
      const row1DirectionHTML = isOn ? `<span class="port-direction">${portDirectionDisplay}</span>` : `<span class="port-direction">-</span>`;

      // Row2/Row3 according to config; for OFF ports, row2 still shows traffic as per your choice (0K/0K) and row3 blank
      const row2Content = renderRowContent(this._config.row2, ctx, isOn);
      const row3Content = renderRowContent(this._config.row3, ctx, isOn);

      const div = document.createElement("div");
      div.className = `port ${speedClass} ${i>=sfpStart?"sfp":""} ${!isOn ? '-' : ''}`;
      div.title =
        `${name}` +
        (ifDescr ? `\nInterface: ${ifDescr}` : "") +
        `\nState: ${isOn ? "UP" : "DOWN"}` +
        `\nSpeed: ${speedText}` +
        (vlan ? `\nVLAN: ${vlan}` : "") +
        `\nRX: ${(rxBps / 1e6).toFixed(2)} Mb/s` +
        `\nTX: ${(txBps / 1e6).toFixed(2)} Mb/s` +
        (port_custom ? `\n${this._config.custom_port_text}: ${port_custom}` : "");
      div.innerHTML = `
        <div class="row1">
          <span class="vlan-dot" style="background:${this._vlanColor(vlan)}"></span>
          <span class="port-num">${i}</span>
          ${row1DirectionHTML}
        </div>
        <div class="port-row">${row2Content}</div>
        <div class="port-row">${row3Content}</div>
        ${poeEnabled?'<div class="poe-indicator">P</div>':''}
      `;
      (i < sfpStart ? copper : sfp).appendChild(div);
    }
  }

  getCardSize() { return this._config.compact_mode ? 5 : 8; }
}

class SwitchPortCardProEditor extends HTMLElement {
  setConfig(c) { this._config = c || {total_ports:8,sfp_start_port:9,show_total_bandwidth:true,max_bandwidth_gbps:100,compact_mode:false,show_system_info:true,show_port_type_labels:true,row2:'rx_tx_live',row3:'speed'}; }

  set hass(hass) {
    this._hass = hass;
    if (!hass || this._last === JSON.stringify(this._config)) return;
    this._last = JSON.stringify(this._config);

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
      </style>
      <div style="padding:16px">
        <div class="row"><label>Title</label><input type="text" data-key="name" value="${this._config.name||''}"></div>
        <div class="row"><label>Device</label>
          <select data-key="device">
            <option value="">-- Select switch --</option>
            ${deviceList.map(d=>`<option value="${d.id}" ${d.id===this._config.device?'selected':''}>${d.name}</option>`).join('')}
          </select>
        </div>
        <div class="row"><label>Fallback Entity</label>
          <select data-key="entity">
            <option value="">-- Optional --</option>
            ${entityList.map(e=>`<option value="${e}" ${e===this._config.entity?'selected':''}>${hass.states[e]?.attributes?.friendly_name||e}</option>`).join('')}
          </select>
        </div>
        <div class="row"><label>Total Ports</label><input type="number" data-key="total_ports" value="${this._config.total_ports||8}"></div>
        <div class="row"><label>First SFP Port</label><input type="number" data-key="sfp_start_port" value="${this._config.sfp_start_port||9}"></div>
        <div class="row"><label>Max Bandwidth (Gbps)</label><input type="number" step="10" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps || 100}"></div>
        <div class="row"><label>Custom value text</label><input type="text" data-key="custom_text" value="${this._config.custom_text||'Custom'}"></div>
        <div class="row"><label>Custom port val. text</label><input type="text" data-key="custom_port_text" value="${this._config.custom_port_text||'Custom Port'}"></div>
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

        <div class="checkbox-row">
          <ha-checkbox data-key="show_total_bandwidth" ${this._config.show_total_bandwidth!==false?'checked':''}></ha-checkbox>
          <span class="checkbox-label">Show Bandwidth Gauge</span>
        </div>
        <div class="checkbox-row">
          <ha-checkbox data-key="compact_mode" ${this._config.compact_mode?'checked':''}></ha-checkbox>
          <span class="checkbox-label">Compact Mode</span>
        </div>

          <!-- Show System Info Switch -->
          <div class="checkbox-row">
            <ha-checkbox data-key="show_system_info" ${this._config.show_system_info !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Show System Info (CPU, Mem, FW, etc.)</span>
          </div>

          <div class="checkbox-row">
            <ha-checkbox data-key="show_port_type_labels" ${this._config.show_port_type_labels !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Show Port Section Title (Copper/Fiber)</span>
          </div>

      </div>
    `;
    // Fix Lovelace editor not showing correct dropdown values
    this.querySelectorAll('select[data-key]').forEach(sel => {
      sel.value = this._config[sel.dataset.key] ?? '';
    });

    // FIXED EVENT LISTENERS
    this.querySelectorAll("[data-key]").forEach(el => {
      el.addEventListener("change", () => {
        const key = el.dataset.key;
        const value = el.tagName === "HA-CHECKBOX" ? el.checked : el.value;
        const finalValue = el.type === "number" ? parseInt(value) || 0 : value;

        this._config = { ...this._config, [key]: finalValue };
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
