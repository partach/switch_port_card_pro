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
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      compact_mode: false,
      show_live_traffic: false,
      show_system_info: true,
      show_port_type_labels: true,
    };
  }

  setConfig(config) {
    this._config = {
      name: "Network Switch",
      total_ports: 8,
      sfp_start_port: 9,
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      compact_mode: false,
      show_live_traffic: false,
      show_system_info: true,
      show_port_type_labels: true,
      ...config
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) this._config = { total_ports:8, sfp_start_port:9, show_total_bandwidth:true, max_bandwidth_gbps:100, compact_mode:false, show_live_traffic:false };
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
          margin-top: 8px; /* adjust to taste */
        }
        .vlan-dot {
          position: absolute;
          top: 2px;
          left: 3px;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          box-shadow: 0 0 1px rgba(0,0,0,0.6);
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
        .port{aspect-ratio:2.6/1;background:var(--light-primary-color);border-radius:8px;display:flex;flex-direction:column;justify-content:center;align-items:center;font-weight:bold;font-size:0.80em;cursor:default;transition:all .2s;position:relative;box-shadow:0 1px 3px rgba(0,0,0,.2),inset 0 1px 0 rgba(255,255,255,.1)}
        .port:hover{transform:scale(1.08);z-index:10}
        .port-num{font-size:0.9em}
        .port-status{font-size:0.7em;margin-top:2px}
        .port.off{background:var(--disabled-background-color);opacity:0.7;color:var(--secondary-text-color)}
        .port.on-10g{background:#1e88e5;color:white}
        .port.on-5g{background:#1565c0;color:white}
        .port.on-2_5g{background:#1976d2;color:white}
        .port.on-1g{background:#4caf50;color:white}
        .port.on-100m{background:#ff9800;color:black}
        .port.on-10m{background:#f44336;color:white}
        .port.sfp{border:2px solid #2196f3!important;box-shadow:0 0 12px rgba(33,150,243,.5)!important}
        .poe-indicator{position:absolute;top:2px;right:4px;font-size:0.7em;font-weight:bold;color:#00ff00;text-shadow:0 0 4px #000}
        .live-traffic{font-size:0.62em;line-height:1.1;opacity:0.92;margin-top:1px}
        .compact .ports-grid{grid-template-columns:repeat(auto-fit,minmax(40px,1fr))}
        .compact .port{aspect-ratio:3.6/1!important;font-size:0.58em!important}
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

    // deterministic color index:
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
      // Detection: if value > 1,000 and unit says "mbit", it's likely Kbps not Mbps
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
      this.shadowRoot.getElementById("system").innerHTML = `
        ${cpu?.state?`<div class="info-box"><div class="info-value">${Math.round(cpu.state)}%</div><div class="info-label">CPU</div></div>`:''}
        ${mem?.state?`<div class="info-box"><div class="info-value">${Math.round(mem.state)}%</div><div class="info-label">Memory</div></div>`:''}
        ${up?.state?`<div class="info-box"><div class="info-value">${this._formatTime(Number(up.state))}</div><div class="info-label">Uptime</div></div>`:''}
        ${host?.state?`<div class="info-box"><div class="info-value">${host.state}</div><div class="info-label">Host</div></div>`:''}
        ${poe?.state!=null && poe.state!=="unknown"?`<div class="info-box"><div class="info-value">${poe.state} W</div><div class="info-label">PoE Total</div></div>`:''}
        ${fw?.state?`<div class="info-box firmware"><div class="info-value">${fw.state}</div><div class="info-label">Firmware</div></div>`:''}
        ${customVal?.state?`<div class="info-box firmware"><div class="info-value">${customVal.state}</div><div class="info-label">Custom</div></div>`:''}`;
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
      
      // Same detection as header - likely Kbps mislabeled as Mbit/s
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
      // Gradient position: 0% = green, 50% = yellow, 100% = red
      fill.style.backgroundPosition = `${pct < 50 ? 0 : (pct - 50) * 2}% 0`;
    } else gauge.style.display="none";

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
      const rxBps = parseInt(
        this._config.show_live_traffic && ent.attributes?.rx_bps_live !== undefined
          ? ent.attributes.rx_bps_live
          : ent.attributes?.rx_bps || 0
      );
      const txBps = parseInt(
        this._config.show_live_traffic && ent.attributes?.tx_bps_live !== undefined
          ? ent.attributes.tx_bps_live
          : ent.attributes?.tx_bps || 0
      );

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

        if (rxBps > txBps*1.8) direction="Down";
        else if (txBps > rxBps*1.8) direction="Up";
      }

      const statusText = this._config.show_live_traffic && (rxBps>100000 || txBps>100000)
        ? `${direction} ${speedText}`.trim()
        : `${direction} ${speedText}`;

      // Format traffic with proper units
      const formatTraffic = (bps) => {
        const mbps = bps / 1e6;
        if (mbps >= 1000) return `${(mbps/1000).toFixed(1)}G`;
        if (mbps >= 1) return `${mbps.toFixed(1)}M`;
        return `${(bps/1e3).toFixed(0)}K`;
      };

      // Always show live traffic div (even if empty) to maintain consistent height
      const liveHTML = this._config.show_live_traffic
        ? (rxBps>1000 || txBps>1000)
          ? `<div class="live-traffic">\u2193${formatTraffic(rxBps)} \u2191${formatTraffic(txBps)}</div>`
          : `<div class="live-traffic">&nbsp;</div>`
        : '';

      const div = document.createElement("div");
      div.className = `port ${speedClass} ${i>=sfpStart?"sfp":""}`;
      div.title =
        `${name}` +
        (ifDescr ? `\nInterface: ${ifDescr}` : "") +
        `\nState: ${isOn ? "UP" : "DOWN"}` +
        `\nSpeed: ${speedText}` +
        (vlan ? `\nVLAN: ${vlan}` : "") +
        `\nRX: ${(rxBps / 1e6).toFixed(2)} Mb/s` +
        `\nTX: ${(txBps / 1e6).toFixed(2)} Mb/s` +
        (port_custom ? `\nCustom: ${port_custom}` : "");
      div.innerHTML = `
        <div class="vlan-dot" style="background:${this._vlanColor(vlan)}"></div>
        <div class="port-num">${i}</div>
        ${liveHTML}
        <div class="port-status">${statusText}</div>
        ${poeEnabled?'<div class="poe-indicator">P</div>':''}
      `;
      (i < sfpStart ? copper : sfp).appendChild(div);
    }
  }

  getCardSize() { return this._config.compact_mode ? 5 : 8; }
}

class SwitchPortCardProEditor extends HTMLElement {
  setConfig(c) { this._config = c || {total_ports:8,sfp_start_port:9,show_total_bandwidth:true,max_bandwidth_gbps:100,compact_mode:false,show_live_traffic:false}; }

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
        <div class="row"><label>Max Bandwidth (Gbps)</label><input type="number" step="10" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps||100}"></div>

        <div class="checkbox-row">
          <ha-checkbox data-key="show_total_bandwidth" ${this._config.show_total_bandwidth!==false?'checked':''}></ha-checkbox>
          <span class="checkbox-label">Show Bandwidth Gauge</span>
        </div>
        <div class="checkbox-row">
          <ha-checkbox data-key="compact_mode" ${this._config.compact_mode?'checked':''}></ha-checkbox>
          <span class="checkbox-label">Compact Mode</span>
        </div>
        <div class="checkbox-row">
          <ha-checkbox data-key="show_live_traffic" ${this._config.show_live_traffic?'checked':''}></ha-checkbox>
          <span class="checkbox-label">Show Live Traffic (Down Up Mbps)</span>
        </div>
          <!-- REQUEST 1: Show System Info Switch -->
          <div class="checkbox-row">
            <ha-checkbox data-key="show_system_info" ${this._config.show_system_info !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Show System Info (CPU, Mem, FW, etc.)</span>
          </div>
          
          <!-- REQUEST 4: Show Port Section Names Switch -->
          <div class="checkbox-row">
            <ha-checkbox data-key="show_port_type_labels" ${this._config.show_port_type_labels !== false ? 'checked' : ''}></ha-checkbox>
            <span class="checkbox-label">Show Port Section Title (Copper/Fiber)</span>
          </div>
      </div>
    `;

    // FIXED EVENT LISTENERS (this is the only part that was broken)
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
