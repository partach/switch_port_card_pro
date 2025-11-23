// ===== SWITCH PORT CARD PRO =====
class SwitchPortCardPro extends HTMLElement {
  static getConfigElement() {
    return document.createElement("switch-port-card-pro-editor");
  }

  static getStubConfig() {
    return {
      entity_prefix: "switch_port_card_pro",
      total_ports: 28,
      sfp_start_port: 25,
      name: "Main Switch",
      copper_label: "COPPER",
      sfp_label: "SFP+",
      show_legend: true,
      show_system_info: true,
      compact_mode: false,
      even_ports_on_top: false,
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100
    };
  }

  setConfig(config) {
    if (!config.entity_prefix) throw new Error("entity_prefix is required");
    const total = parseInt(config.total_ports || 28, 10);
    const sfpStart = parseInt(config.sfp_start_port || 25, 10);
    if (isNaN(total) || total < 1) throw new Error("total_ports must be valid");
    if (isNaN(sfpStart)) throw new Error("sfp_start_port must be valid");

    this._config = {
      name: "Switch Ports",
      copper_label: "COPPER",
      sfp_label: "SFP+",
      show_legend: true,
      show_system_info: true,
      compact_mode: false,
      even_ports_on_top: false,
      show_total_bandwidth: true,
      max_bandwidth_gbps: 100,
      ...config
    };

    this._total = total;
    this._sfpStart = sfpStart;
    this._copperPorts = Array.from({ length: sfpStart - 1 }, (_, i) => i + 1);
    this._sfpPorts = Array.from({ length: total - sfpStart + 1 }, (_, i) => sfpStart + i);
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _openMoreInfo(entityId) {
    if (!entityId) return;
    const event = new Event("hass-more-info", { bubbles: true, composed: true });
    event.detail = { entityId };
    this.dispatchEvent(event);
  }

  _getPortStatus(port) {
    const prefix = this._config.entity_prefix;
    const statusEnt = this._hass?.states[`sensor.${prefix}_port_${port}`];
    if (!statusEnt) return "UNAVAIL";
    const state = statusEnt.state?.toLowerCase();
    if (state === "down") return "DOWN";
    if (state === "up") return "10G";
    return "UNAVAIL";
  }

  _getColor(status) {
    if (status === "DOWN") return "#666666";
    if (status === "UNAVAIL") return "#444444";
    if (status.includes("10G")) return "#1156f3";
    if (status.includes("1G")) return "#2c6f50";
    if (status.includes("100M")) return "#ee6b35";
    return "#ff6b35";
  }

  _renderPort(port, status) {
    const c = this._config.compact_mode;
    const isSfp = port >= this._sfpStart;
    const size = c ? 28 : 32;
    const gap = c ? 1 : 2;
    const opacity = status === "DOWN" || status === "UNAVAIL" ? 0.6 : 1;
    const bg = this._getColor(status);
    const tooltip = `Port ${port}\nStatus: ${status}`;

    return `
      <div style="margin:0 ${gap}px;flex:0 0 ${size}px;">
        <div style="font-size:${c?7:8}px;color:#888;margin-bottom:2px;text-align:center;">${port}</div>
        <div style="
          width:${size}px;height:${size}px;
          background:${bg};color:#fff;
          border-radius:${c?6:8}px;
          display:flex;align-items:center;justify-content:center;
          font-weight:bold;font-size:${c?9:11}px;
          cursor:pointer;opacity:${opacity};
          transition:transform .1s;
        "
        title="${tooltip}"
        onclick="this.closest('switch-port-card-pro')._openMoreInfo('sensor.${this._config.entity_prefix}_port_${port}')"
        onmouseenter="this.style.transform='scale(1.1)'"
        onmouseleave="this.style.transform='scale(1)'"
        >
          ${status === "10G" ? "10G" : status === "DOWN" ? "×" : "?"}
        </div>
      </div>`;
  }

  _renderCopperRows() {
    if (this._copperPorts.length === 0) return "";
    const c = this._config.compact_mode;
    const evenOnTop = this._config.even_ports_on_top;
    const top = evenOnTop
      ? this._copperPorts.filter(p => p % 2 === 0)
      : this._copperPorts.filter(p => p % 2 === 1);
    const bottom = evenOnTop
      ? this._copperPorts.filter(p => p % 2 === 1)
      : this._copperPorts.filter(p => p % 2 === 0);

    let html = `<div style="margin:${c?6:10}px 0 ${c?4:8}px;color:#999;font-size:${c?10:12}px;font-weight:600;text-align:center;">
                  ${this._config.copper_label}
                </div>`;

    [top, bottom].forEach(row => {
      html += `<div style="display:flex;justify-content:center;gap:${c?2:4}px;margin-bottom:${c?2:6}px;">`;
      row.forEach(p => html += this._renderPort(p, this._getPortStatus(p)));
      html += `</div>`;
    });

    return html;
  }

  _renderSfp() {
    if (this._sfpPorts.length === 0) return "";
    const c = this._config.compact_mode;
    let html = `<div style="display:flex;align-items:center;gap:8px;margin-top:8px;">`;
    html += `<div style="color:#999;font-weight:600;font-size:${c?10:11}px;">${this._config.sfp_label}</div>`;
    this._sfpPorts.forEach(p => html += this._renderPort(p, this._getPortStatus(p)));
    html += `</div>`;
    return html;
  }

  _renderTotalBandwidth() {
    if (!this._config.show_total_bandwidth) return "";
    const prefix = this._config.entity_prefix;
    const ent = this._hass?.states[`sensor.${prefix}_bandwidth`];
    const val = ent?.state ? parseFloat(ent.state) : 0;
    const max = (this._config.max_bandwidth_gbps || 100) * 1000;
    const percent = Math.min(100, (val / max) * 100);
    const gbps = (val / 1000).toFixed(2);

    const color = percent > 90 ? "#f44336" : percent > 70 ? "#ff9800" : "#2c6f50";

    return `
      <div style="margin:16px 0;text-align:center;">
        <div style="font-size:14px;color:#999;margin-bottom:6px;">Total Switch Traffic</div>
        <div style="font-size:28px;font-weight:bold;color:${color};">${gbps} Gbps</div>
        <div style="width:100%;max-width:300px;margin:8px auto;height:12px;background:#333;border-radius:6px;overflow:hidden;">
          <div style="height:100%;width:${percent}%;background:${color};transition:width .4s;"></div>
        </div>
      </div>`;
  }

  _renderSystemBars() {
    const prefix = this._config.entity_prefix;
    const cpu = this._hass?.states[`sensor.${prefix}_cpu`]?.state || 0;
    const mem = this._hass?.states[`sensor.${prefix}_memory`]?.state || 0;
    const uptime = this._hass?.states[`sensor.${prefix}_uptime`]?.state || "—";
    const name = this._hass?.states[`sensor.${prefix}_name`]?.state || "Switch";

    return `
      <div style="margin-top:12px;padding-top:12px;border-top:1px solid #444;font-size:13px;color:#aaa;">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
          <span>CPU: ${cpu}%</span>
          <span>Memory: ${mem}%</span>
          <span>Uptime: ${uptime}h</span>
        </div>
        <div style="text-align:center;color:#e8e8e8;font-size:14px;">${name}</div>
      </div>`;
  }

  _render() {
    if (!this._hass) {
      this.innerHTML = `<ha-card><div style="padding:20px;text-align:center;color:#aaa;">Loading...</div></ha-card>`;
      return;
    }

    const dark = this._hass.themes?.darkMode ?? false;
    const bg = dark ? "#1e1e1e" : "#fafafa";
    const text = dark ? "#e8e8e8" : "#212121";
    const border = dark ? "#333" : "#e0e0e0";

    this.innerHTML = `
      <ha-card style="padding:20px;background:${bg};border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,${dark?0.5:0.1});border:1px solid ${border};font-family:system-ui;">
        <div style="text-align:center;font-size:20px;font-weight:600;color:${text};margin-bottom:16px;">
          ${this._config.name}
        </div>

        ${this._renderTotalBandwidth()}

        ${this._renderCopperRows()}
        ${this._renderSfp()}

        ${this._config.show_system_info ? this._renderSystemBars() : ""}
      </ha-card>`;
  }

  getCardSize() { return 5; }
}

customElements.define("switch-port-card-pro", SwitchPortCardPro);
customElements.define("switch-port-card-pro-editor", class extends HTMLElement {
  setConfig(config) { this._config = config; }
  set hass(hass) { this._hass = hass; }
  connectedCallback() {
    this.innerHTML = `<div style="padding:20px;color:#888;font-style:italic;">Switch Port Card Pro<br>Uses integration: switch_port_card_pro</div>`;
  }
});
