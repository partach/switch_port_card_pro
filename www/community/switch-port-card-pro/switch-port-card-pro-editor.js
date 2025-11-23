class SwitchPortCardProEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) this._render();
  }

  _render() {
    if (!this._config) return;

    const prefix = this._config.entity_prefix || "switch_port_card_pro";

    this.innerHTML = `
      <style>
        .container { padding: 16px; font-family: var(--paper-font-body1_-_font-family); }
        .row { display: flex; gap: 12px; margin-bottom: 12px; align-items: center; }
        .row label { flex: 0 0 160px; font-weight: 500; }
        .row input, .row select { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        .checkbox { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
        .help { font-size: 12px; color: #666; margin-top: 4px; }
        .section { margin: 20px 0 8px; font-weight: 600; color: var(--primary-text-color); border-bottom: 1px solid #ddd; padding-bottom: 4px; }
      </style>
      <div class="container">

        <div class="section">Basic Settings</div>
        <div class="row">
          <label>Card Title</label>
          <input type="text" data-key="name" value="${this._config.name || 'Main Switch'}">
        </div>

        <div class="row">
          <label>Entity Prefix</label>
          <input type="text" data-key="entity_prefix" value="${prefix}">
          <div class="help">From your integration (e.g. switch_port_card_pro)</div>
        </div>

        <div class="row">
          <label>Total Ports</label>
          <input type="number" min="1" max="128" data-key="total_ports" value="${this._config.total_ports || 28}">
        </div>

        <div class="row">
          <label>First SFP+ Port</label>
          <input type="number" min="1" max="128" data-key="sfp_start_port" value="${this._config.sfp_start_port || 25}">
        </div>

        <div class="row">
          <label>Copper Label</label>
          <input type="text" data-key="copper_label" value="${this._config.copper_label || 'COPPER'}">
        </div>

        <div class="row">
          <label>SFP+ Label</label>
          <input type="text" data-key="sfp_label" value="${this._config.sfp_label || 'SFP+'}">
        </div>

        <div class="section">Display Options</div>
        <div class="checkbox">
          <input type="checkbox" data-key="show_total_bandwidth" ${this._config.show_total_bandwidth !== false ? 'checked' : ''}>
          <label>Show Total Bandwidth Gauge</label>
        </div>

        <div class="row" style="display:${this._config.show_total_bandwidth !== false ? 'flex' : 'none'};" id="maxbw">
          <label>Max Bandwidth (Gbps)</label>
          <input type="number" step="10" min="10" max="1000" data-key="max_bandwidth_gbps" value="${this._config.max_bandwidth_gbps || 100}">
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="show_system_info" ${this._config.show_system_info !== false ? 'checked' : ''}>
          <label>Show CPU / Memory / Uptime</label>
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="compact_mode" ${this._config.compact_mode ? 'checked' : ''}>
          <label>Compact Mode</label>
        </div>

        <div class="checkbox">
          <input type="checkbox" data-key="even_ports_on_top" ${this._config.even_ports_on_top ? 'checked' : ''}>
          <label>Even ports on top row (2,4,6…)</label>
        </div>

        <div style="margin-top:16px;padding:12px;background:#f9f9f9;border-radius:6px;font-size:13px;color:#555;">
          <strong>Expected entities:</strong><br>
          • sensor.${prefix}_bandwidth<br>
          • sensor.${prefix}_cpu<br>
          • sensor.${prefix}_memory<br>
          • sensor.${prefix}_uptime<br>
          • sensor.${prefix}_port_1 … _${this._config.total_ports || 28}
        </div>
      </div>
    `;

    // Sync max bandwidth row visibility
    const bwCheck = this.querySelector('[data-key="show_total_bandwidth"]');
    const bwRow = this.querySelector('#maxbw');
    bwCheck.addEventListener('change', () => {
      bwRow.style.display = bwCheck.checked ? 'flex' : 'none';
    });

    // Change handler
    this.querySelectorAll('input').forEach(el => {
      el.addEventListener('change', (e) => {
        const key = e.target.dataset.key;
        let value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
        if (e.target.type === 'number') value = parseInt(value) || 0;

        const newConfig = { ...this._config, [key]: value };
        this._config = newConfig;

        const event = new Event('config-changed', { bubbles: true, composed: true });
        event.detail = { config: newConfig };
        this.dispatchEvent(event);
      });
    });

    this._initialized = true;
  }
}

customElements.define('switch-port-card-pro-editor', SwitchPortCardProEditor);
