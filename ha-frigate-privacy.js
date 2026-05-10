/* HA Tools split — ha-frigate-privacy v4.0.0 (2026-05-10) — single-tool standalone repo */
(function() {
'use strict';

// XSS protection helper (reuse global from panel, fallback for standalone)
const _esc = window._haToolsEsc || ((s) => typeof s === 'string' ? s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]) : (s ?? ''));

// -- HA Tools Persistence (stub -- full impl in ha-tools-panel.js) --
window._haToolsPersistence = window._haToolsPersistence || { _cache: {}, _hass: null, setHass(h) { this._hass = h; }, async save(k, d) { try { localStorage.setItem('ha-frigate-privacy-' + k, JSON.stringify(d)); } catch(e) { console.debug('[ha-frigate-privacy] caught:', e); } }, async load(k) { try { const r = localStorage.getItem('ha-frigate-privacy-' + k); return r ? JSON.parse(r) : null; } catch(e) { return null; } }, loadSync(k) { try { const r = localStorage.getItem('ha-frigate-privacy-' + k); return r ? JSON.parse(r) : null; } catch(e) { return null; } } };


/* ===== HA Tools split — inline shared infrastructure ===== */
// Bento Design System CSS (inline copy — keeps tool standalone)
if (typeof window !== 'undefined' && !window.HAToolsBentoCSS) {
  window.HAToolsBentoCSS = `
/* ═══════════════════════════════════════════════
   HA Tools — Bento Design System v1.0
   ═══════════════════════════════════════════════ */

/* ── CSS Custom Properties ───────────────────── */
:host {
  /* Primary palette */
  --bento-primary: #3B82F6;
  --bento-primary-hover: #2563EB;
  --bento-primary-light: rgba(59, 130, 246, 0.08);
  --bento-success: #10B981;
  --bento-success-light: rgba(16, 185, 129, 0.08);
  --bento-error: #EF4444;
  --bento-error-light: rgba(239, 68, 68, 0.08);
  --bento-warning: #F59E0B;
  --bento-warning-light: rgba(245, 158, 11, 0.08);

  /* Theme — maps to HA theme vars with light fallbacks */
  --bento-bg: var(--primary-background-color, #F8FAFC);
  --bento-card: var(--card-background-color, #FFFFFF);
  --bento-border: var(--divider-color, #E2E8F0);
  --bento-text: var(--primary-text-color, #1E293B);
  --bento-text-secondary: var(--secondary-text-color, #64748B);
  --bento-text-muted: var(--disabled-text-color, #94A3B8);

  /* Radii */
  --bento-radius-xs: 6px;
  --bento-radius-sm: 10px;
  --bento-radius-md: 16px;

  /* Shadows */
  --bento-shadow-sm: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.06);
  --bento-shadow-md: 0 4px 12px rgba(0,0,0,0.05), 0 2px 4px rgba(0,0,0,0.04);
  --bento-shadow-lg: 0 8px 25px rgba(0,0,0,0.06), 0 4px 10px rgba(0,0,0,0.04);

  /* Transition */
  --bento-transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  /* Typography */
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: block;
  color: var(--bento-text);
}

/* ── Dark mode ───────────────────────────────── */
@media (prefers-color-scheme: dark) {
  :host {
    --bento-bg: var(--primary-background-color, #1a1a2e);
    --bento-card: var(--card-background-color, #16213e);
    --bento-border: var(--divider-color, #2a2a4a);
    --bento-text: var(--primary-text-color, #e0e0e0);
    --bento-text-secondary: var(--secondary-text-color, #a0a0b0);
    --bento-text-muted: var(--disabled-text-color, #6a6a7a);
    --bento-shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
    --bento-shadow-md: 0 4px 12px rgba(0,0,0,0.4);
    --bento-primary-light: rgba(59,130,246,0.15);
    --bento-success-light: rgba(16,185,129,0.15);
    --bento-error-light: rgba(239,68,68,0.15);
    --bento-warning-light: rgba(245,158,11,0.15);
    color-scheme: dark !important;
  }
  .card, .card-container, .main-card, .exporter-card, .security-card, .reports-card, .storage-card, .chore-card, .cry-card, .backup-card, .network-card, .sentence-card, .energy-card, .panel-card {
    background: var(--bento-card) !important; color: var(--bento-text) !important; border-color: var(--bento-border) !important;
  }
  input, select, textarea { background: var(--bento-bg); color: var(--bento-text); border-color: var(--bento-border); }
  .stat, .stat-card, .summary-card, .metric-card, .kpi-card, .health-card { background: var(--bento-bg); border-color: var(--bento-border); }
  .tab-content, .section { color: var(--bento-text); }
  table th { background: var(--bento-bg); color: var(--bento-text-secondary); border-color: var(--bento-border); }
  table td { color: var(--bento-text); border-color: var(--bento-border); }
  tr:hover td { background: rgba(59,130,246,0.08); }
  .empty-state, .no-data { color: var(--bento-text-secondary); }
  .schedule-section, .settings-section, .detail-panel, .details, .device-detail { background: var(--bento-bg); border-color: var(--bento-border); }
  .addon-list, .content-item { background: rgba(255,255,255,0.05); }
  .chart-container { background: var(--bento-bg); border-color: var(--bento-border); }
  pre, code { background: #1e293b !important; color: #e2e8f0 !important; }
}

/* ── Reset ───────────────────────────────────── */
* { box-sizing: border-box; }

/* ── Main Card Wrapper ───────────────────────── */
.card {
  background: var(--bento-card);
  border: 1px solid var(--bento-border);
  border-radius: var(--bento-radius-md);
  box-shadow: var(--bento-shadow-sm);
  color: var(--bento-text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ── Header ──────────────────────────────────── */
.header {
  padding: 16px 20px 0;
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-icon { font-size: 22px; }
.header-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--bento-text);
}
.header-badge {
  margin-left: auto;
  background: var(--bento-border);
  color: var(--bento-text-secondary);
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 20px;
  font-weight: 500;
}
.content { padding: 16px 20px 20px; }

/* ── Tabs (Bento unified) ────────────────────── */
.tabs, .tab-bar, .tab-nav, .tab-header {
  display: flex !important;
  gap: 4px !important;
  border-bottom: 2px solid var(--bento-border, var(--divider-color, #334155)) !important;
  padding: 0 4px !important;
  margin-bottom: 20px !important;
  overflow-x: auto !important; overflow-y: hidden !important; -webkit-overflow-scrolling: touch !important;
  flex-wrap: nowrap !important;
}
.tab, .tab-btn, .tab-button, .dtab {
  padding: 10px 18px !important;
  border: none !important;
  background: transparent !important;
  cursor: pointer !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  font-family: 'Inter', sans-serif !important;
  color: var(--bento-text-secondary, var(--secondary-text-color, #94A3B8)) !important;
  border-bottom: 2px solid transparent !important;
  margin-bottom: -2px !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
  white-space: nowrap !important;
  border-radius: 0 !important;
  flex: none !important;
}
.tab:hover, .tab-btn:hover, .tab-button:hover, .dtab:hover {
  color: var(--bento-primary, #3B82F6) !important;
  background: rgba(59, 130, 246, 0.08) !important;
}
.tab.active, .tab-btn.active, .tab-button.active, .dtab.active {
  color: var(--bento-primary, #3B82F6) !important;
  border-bottom-color: var(--bento-primary, #3B82F6) !important;
  background: rgba(59, 130, 246, 0.04) !important;
  font-weight: 600 !important;
}

/* ── Tab content animation ───────────────────── */
.tab-content {
  display: block;
}
.tab-content.active {
  animation: bentoFadeIn 0.3s ease-out;
}
@keyframes bentoFadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Stat / KPI cards ────────────────────────── */
.stat-card, .stat-item, .metric-card, .kpi-card {
  background: var(--bento-card, var(--card-background-color, #1E293B)) !important;
  border: 1px solid var(--bento-border, var(--divider-color, #334155)) !important;
  border-radius: var(--bento-radius-sm, 10px) !important;
  padding: 16px !important;
  text-align: center !important;
  transition: var(--bento-transition);
}
.stat-card:hover, .stat-item:hover, .metric-card:hover, .kpi-card:hover {
  box-shadow: var(--bento-shadow-md);
}
.stat-icon { font-size: 20px; margin-bottom: 4px; }
.stat-value, .stat-val, .metric-value, .kpi-val {
  font-size: 22px;
  font-weight: 700;
  color: var(--bento-text);
}
.stat-label, .stat-lbl, .metric-label, .kpi-lbl {
  font-size: 11px;
  color: var(--bento-text-secondary);
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 500;
}

/* ── Overview grid (2×2 stat layout) ─────────── */
.overview-grid, .stats-grid, .summary-grid, .stat-cards, .kpi-grid, .metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 16px;
}

/* ── Section headers ─────────────────────────── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: var(--bento-text-secondary);
  text-transform: uppercase;
  letter-spacing: .5px;
  margin: 12px 0 8px;
}

/* ── Loading / Empty / Info ──────────────────── */
.loading-bar {
  height: 3px;
  background: linear-gradient(90deg, var(--bento-primary), transparent);
  border-radius: 2px;
  animation: bentoLoad 1s infinite;
  margin-bottom: 8px;
}
@keyframes bentoLoad { 0% { background-position: 0; } 100% { background-position: 200px; } }

.empty-state, .no-data, .no-results {
  text-align: center;
  color: var(--bento-text-secondary);
  padding: 32px 16px;
  font-size: 13px;
  background: var(--bento-bg);
  border-radius: var(--bento-radius-sm);
}
.info-note, .tip-box {
  font-size: 12px;
  color: var(--bento-text-secondary);
  background: var(--bento-bg);
  border-radius: var(--bento-radius-sm);
  padding: 8px 10px;
  border-left: 3px solid var(--bento-primary);
  margin-top: 8px;
}
.last-updated {
  font-size: 11px;
  color: var(--bento-text-muted);
  text-align: right;
  margin-top: 8px;
}

/* ── Buttons ─────────────────────────────────── */
.refresh-btn {
  background: var(--bento-border);
  border: none;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--bento-text-secondary);
  cursor: pointer;
  font-weight: 500;
  transition: var(--bento-transition);
}
.refresh-btn:hover { background: var(--bento-primary); color: white; }

.toggle-btn, .action-btn {
  background: var(--bento-primary);
  border: none;
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  color: white;
  cursor: pointer;
  font-weight: 500;
  transition: var(--bento-transition);
}
.toggle-btn:hover, .action-btn:hover { opacity: .85; }

.send-btn, .btn-primary {
  width: 100%;
  background: var(--bento-primary);
  color: white;
  border: none;
  border-radius: 8px;
  padding: 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--bento-transition);
}
.send-btn:hover, .btn-primary:hover {
  background: var(--bento-primary-hover);
  transform: translateY(-1px);
}
.send-btn:active, .btn-primary:active { transform: translateY(0); }
.send-btn:disabled, .btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

/* ── Badges / Status ─────────────────────────── */
.badge, .status-badge, .tag, .chip {
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  display: inline-block;
}
.badge-ok, .badge-success { background: var(--bento-success-light); color: var(--bento-success); }
.badge-er, .badge-error   { background: var(--bento-error-light);   color: var(--bento-error); }
.badge-warn, .badge-warning { background: var(--bento-warning-light); color: var(--bento-warning); }
.badge-info { background: var(--bento-primary-light); color: var(--bento-primary); }

/* ── Count badges (inline) ───────────────────── */
.count-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 20px;
}
.error-badge { background: rgba(239,68,68,0.13); color: var(--bento-error); }
.warn-badge  { background: rgba(245,158,11,0.13); color: var(--bento-warning); }
.info-badge  { background: rgba(59,130,246,0.13); color: var(--bento-primary); }
.ok-badge    { background: rgba(16,185,129,0.13); color: var(--bento-success); }

/* ── Tables ───────────────────────────────────── */
table { width: 100%; border-collapse: separate; border-spacing: 0; }
th {
  background: var(--bento-bg);
  color: var(--bento-text-secondary);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 10px 14px;
  text-align: left;
  border-bottom: 2px solid var(--bento-border);
}
td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--bento-border);
  color: var(--bento-text);
  font-size: 13px;
}
tr:hover td { background: var(--bento-primary-light); }

/* ── Forms / Inputs ──────────────────────────── */
input, select, textarea {
  padding: 8px 12px;
  border: 1.5px solid var(--bento-border);
  border-radius: var(--bento-radius-xs);
  background: var(--bento-card);
  color: var(--bento-text);
  font-size: 13px;
  font-family: 'Inter', sans-serif;
  transition: var(--bento-transition);
  outline: none;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--bento-primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

/* ── Code blocks ─────────────────────────────── */
code {
  background: var(--bento-border);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}
pre {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 8px;
  font-size: 12px;
  overflow-x: auto;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Grid layouts ────────────────────────────── */
.schedule-grid, .send-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.schedule-card, .send-card, .info-card {
  background: var(--bento-bg);
  border: 1px solid var(--bento-border);
  border-radius: var(--bento-radius-sm);
  padding: 14px;
}

/* ── Log entries ─────────────────────────────── */
.log-entry {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 4px 6px;
  padding: 8px;
  border-radius: var(--bento-radius-sm);
  margin-bottom: 4px;
  font-size: 12px;
  min-width: 0;
  overflow: hidden;
}
.error-entry { background: var(--bento-error-light); border: 1px solid rgba(239,68,68,0.13); }
.warn-entry  { background: var(--bento-warning-light); border: 1px solid rgba(245,158,11,0.13); }
.log-time { color: var(--bento-text-muted); flex-shrink: 0; }
.log-domain {
  font-weight: 600;
  flex-shrink: 1;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: break-all;
}
.error-domain { color: var(--bento-error); }
.warn-domain  { color: var(--bento-warning); }
.log-msg {
  color: var(--bento-text-secondary);
  flex-basis: 100%;
  word-break: break-word;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  min-width: 0;
}

/* ── Send status ─────────────────────────────── */
.send-status {
  padding: 10px 14px;
  border-radius: var(--bento-radius-sm);
  margin-top: 12px;
  font-size: 13px;
  font-weight: 500;
  text-align: center;
}
.send-status.sending { background: var(--bento-primary-light); color: var(--bento-primary); }
.send-status.success { background: var(--bento-success-light); color: var(--bento-success); }
.send-status.error   { background: var(--bento-error-light);   color: var(--bento-error); }

/* ── Scrollbar ───────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--bento-border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--bento-text-muted); }

/* ── Animations ──────────────────────────────── */
@keyframes bentoSpin { to { transform: rotate(360deg); } }
@keyframes bentoPulse { 0%,100% { opacity: 1; } 50% { opacity: .5; } }

/* ── Mobile — 768 px ─────────────────────────── */
@media (max-width: 768px) {
  .content { padding: 12px; }
  .tabs { flex-wrap: nowrap !important; overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; gap: 2px !important; }
  .tab, .tab-button, .tab-btn { padding: 6px 10px !important; font-size: 12px !important; white-space: nowrap !important; }
  .overview-grid, .stats-grid, .summary-grid, .stat-cards, .kpi-grid, .metrics-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .stat-value, .stat-val, .kpi-val, .metric-val { font-size: 18px !important; }
  .stat-label, .stat-lbl, .kpi-lbl, .metric-lbl { font-size: 10px !important; }
  .send-grid, .schedule-grid { grid-template-columns: 1fr; }
  .log-entry { flex-wrap: wrap; gap: 2px 6px; }
  .log-domain { max-width: 60%; font-size: 11px; }
  .log-msg { flex-basis: 100%; max-width: 100%; overflow-wrap: anywhere; font-size: 11px; }
  pre { white-space: pre-wrap; word-break: break-all; max-width: calc(100vw - 80px); overflow-x: auto; }
  .panels, .board { flex-direction: column; }
  .column { min-width: unset; }
  h2 { font-size: 18px; }
  h3 { font-size: 15px; }
}

/* ── Mobile — 480 px ─────────────────────────── */
@media (max-width: 480px) {
  .tabs { gap: 1px !important; }
  .tab, .tab-button, .tab-btn { padding: 5px 8px !important; font-size: 11px !important; }
  .overview-grid, .stats-grid, .summary-grid { grid-template-columns: 1fr 1fr; }
  .stat-value, .stat-val, .kpi-val { font-size: 16px !important; }
}
`;
}
// XSS escape singleton (idempotent)
if (typeof window !== 'undefined') {
  window._haToolsEsc = window._haToolsEsc || (function(){
    var MAP = {};
    MAP[String.fromCharCode(38)] = '&amp;';
    MAP[String.fromCharCode(60)] = '&lt;';
    MAP[String.fromCharCode(62)] = '&gt;';
    MAP[String.fromCharCode(34)] = '&quot;';
    MAP[String.fromCharCode(39)] = '&#39;';
    return function(s){ return typeof s === 'string' ? s.replace(/[&<>"']/g, function(c){ return MAP[c]; }) : (s == null ? '' : s); };
  })();
}
// Universal donate footer injector — guarantees the support box appears
// on every split-tool card regardless of internal render state.
if (typeof window !== 'undefined' && !window.__haToolsSplitDonateInjector) {
  window.__haToolsSplitDonateInjector = true;
  var SPLIT_TAGS = ['ha-purge-cache','ha-yaml-checker','ha-data-exporter','ha-baby-tracker','ha-chore-tracker','ha-energy-optimizer','ha-energy-insights','ha-energy-email','ha-log-email','ha-smart-reports','ha-network-map','ha-trace-viewer','ha-automation-analyzer','ha-storage-monitor','ha-backup-manager','ha-security-check','ha-device-health','ha-sentence-manager','ha-encoding-fixer','ha-entity-renamer','ha-frigate-privacy','ha-vacuum-water-monitor'];
  var DONATE_HTML = ''
    + '<div class="donate-section" data-source="ha-tools-split-injector">'
    + '  <div class="donate-text">'
    + '    <h3>❤️ Support HA Tools Development</h3>'
    + '    <p>If this tool makes your Home Assistant life easier, consider supporting the project. Every coffee motivates further development!</p>'
    + '  </div>'
    + '  <div class="donate-buttons">'
    + '    <a class="donate-btn coffee" href="https://buymeacoffee.com/macsiem" target="_blank" rel="noopener noreferrer">☕ Buy Me a Coffee</a>'
    + '    <a class="donate-btn paypal" href="https://www.paypal.com/donate/?hosted_button_id=Y967H4PLRBN8W" target="_blank" rel="noopener noreferrer">💳 PayPal</a>'
    + '  </div>'
    + '</div>';
  function injectAll() {
    SPLIT_TAGS.forEach(function(tag){
      document.querySelectorAll(tag).forEach(function(el){
        if (!el.shadowRoot) return;
        if (el.shadowRoot.querySelector('.donate-section')) return;
        var target = el.shadowRoot.querySelector('.card, .card-container, .main-card, [class$="-card"]') || el.shadowRoot.firstElementChild || el.shadowRoot;
        try { target.insertAdjacentHTML('beforeend', DONATE_HTML); } catch(e) {}
      });
    });
  }
  // Initial + periodic for first 60s; then MutationObserver for later mounts.
  setTimeout(injectAll, 250);
  var pollCount = 0;
  var pollInterval = setInterval(function(){
    injectAll();
    if (++pollCount >= 30) {
      clearInterval(pollInterval);
      try {
        var obs = new MutationObserver(function(){ injectAll(); });
        obs.observe(document.body, { childList: true, subtree: true });
      } catch(e) {}
    }
  }, 2000);
}
/* ============================================================ */

class HaFrigatePrivacy extends HTMLElement {
  constructor() {
    super();
    this._toolId = this.tagName.toLowerCase().replace('ha-', '');
    this._lang = (navigator.language || '').startsWith('pl') ? 'pl' : 'en';
    this.attachShadow({ mode: 'open' });
    this._lastRenderTime = 0;
    this._renderScheduled = false;
    this._firstHassRender = false;
    this._lastHtml = '';
    this._hass = null;
    this._config = {};
    this._activeTab = 'control';
    this._frigateRunning = null;
    this._cameras = [];
    this._selectedCameras = new Set();
    this._customMinutes = 30;
    this._privacyActive = false;
    this._privacyEndTime = null;
    this._privacyTimerInterval = null;
    this._schedules = [];
    this._scheduleForm = { enabled: true, days: [1,2,3,4,5], startHour: 18, startMin: 0, endHour: 20, endMin: 0, repeat: true, label: '' };
    this._editingScheduleIdx = null;
    this._helpersChecked = false;
    this._lastScheduleCheck = 0;
    this._history = [];
    // Notification settings
    this._notifyEnabled = true;
    this._notifyService = 'persistent_notification'; // or 'notify.mobile_app_xxx'
    this._notifyBeforeEndMin = 5;
    this._warningSent = false;
    this._privacyCameras = 'all'; // cameras string for active session
    this._privacyStartedMin = 0;
  }

  static getConfigElement() {
    return document.createElement('ha-frigate-privacy-editor');
  }

  getCardSize() { return 6; }

  static getStubConfig() {
    return {
      type: 'custom:ha-frigate-privacy',
      title: 'Frigate Privacy',
      frigate_addon_id: 'ccab4aaf_frigate',
      frigate_running_entity: 'binary_sensor.frigate_running',
      cameras: []
    };
  }

  _sanitize(str) {
    if (!str) return str;
    try { return decodeURIComponent(escape(str)); } catch(e) { return str; }
  }

  get _t() {
    const T = {
      pl: {
        title: 'Frigate Privacy',
        tabControl: 'Sterowanie',
        tabSchedule: 'Harmonogram',
        tabHistory: 'Historia',
        frigateStatus: 'Status Frigate',
        running: 'Dziala',
        stopped: 'Zatrzymany',
        unknown: 'Nieznany',
        selectCameras: 'Wybierz kamery',
        allCameras: 'Wszystkie kamery',
        quickPause: 'Szybka pauza',
        customDuration: 'Wlasny czas (min)',
        pauseFrigate: 'Wstrzymaj Frigate',
        resumeFrigate: 'Wznow Frigate',
        privacyActive: 'Tryb prywatnosci aktywny',
        remainingTime: 'Pozostaly czas',
        cancelPrivacy: 'Anuluj prywatnosc',
        scheduleTitle: 'Zaplanowane okna prywatnosci',
        addSchedule: 'Dodaj harmonogram',
        editSchedule: 'Edytuj harmonogram',
        saveSchedule: 'Zapisz',
        cancelEdit: 'Anuluj',
        deleteSchedule: 'Usun',
        days: ['Pn', 'Wt', 'Sr', 'Cz', 'Pt', 'So', 'Nd'],
        daysLong: ['Poniedzialek', 'Wtorek', 'Sroda', 'Czwartek', 'Piatek', 'Sobota', 'Niedziela'],
        from: 'Od',
        to: 'Do',
        repeat: 'Powtarzaj',
        oneTime: 'Jednorazowo',
        label: 'Etykieta',
        enabled: 'Wlaczony',
        disabled: 'Wylaczony',
        noSchedules: 'Brak zaplanowanych okien prywatnosci',
        historyTitle: 'Historia prywatnosci',
        noHistory: 'Brak historii',
        started: 'Uruchomiono',
        duration: 'Czas trwania',
        min: 'min',
        manualPause: 'Pauza reczna',
        scheduled: 'Zaplanowane',
        cancelled: 'Anulowano',
        completed: 'Zakonczone',
        errorCallScript: 'Blad wywolania skryptu prywatnosci',
        errorStopAddon: 'Blad zatrzymywania Frigate',
        errorStartAddon: 'Blad uruchamiania Frigate',
        noCamerasFound: 'Nie znaleziono kamer Frigate',
        privacyModeStarted: 'Tryb prywatnosci uruchomiony na',
        frigateResumed: 'Frigate wznowiony',
        tabSettings: 'Ustawienia',
        notifications: 'Powiadomienia',
        notifyEnabled: 'Wlacz powiadomienia',
        notifyService: 'Usluga powiadomien',
        notifyPersistent: 'Powiadomienia HA (persistent)',
        notifyMobile: 'Aplikacja mobilna',
        notifyBeforeEnd: 'Powiadom przed koncem (min)',
        extendTime: 'Wydluz czas',
        extendBy: 'Wydluz o',
        privacyEndingSoon: 'Prywatnosc konczy sie za',
        forCameras: 'dla kamer',
        allCamerasLabel: 'wszystkie kamery',
        notifExtendQuestion: 'Wydluz?',
        privacyExtended: 'Prywatnosc wydluzona o',
        scheduleReminder: 'Przypomnienie: zaplanowana prywatnosc',
        startsIn: 'zaczyna sie za',
        endsIn: 'konczy sie za',
      },
      en: {
        title: 'Frigate Privacy',
        tabControl: 'Control',
        tabSchedule: 'Schedule',
        tabHistory: 'History',
        frigateStatus: 'Frigate Status',
        running: 'Running',
        stopped: 'Stopped',
        unknown: 'Unknown',
        selectCameras: 'Select cameras',
        allCameras: 'All cameras',
        quickPause: 'Quick pause',
        customDuration: 'Custom duration (min)',
        pauseFrigate: 'Pause Frigate',
        resumeFrigate: 'Resume Frigate',
        privacyActive: 'Privacy mode active',
        remainingTime: 'Time remaining',
        cancelPrivacy: 'Cancel privacy',
        scheduleTitle: 'Scheduled privacy windows',
        addSchedule: 'Add schedule',
        editSchedule: 'Edit schedule',
        saveSchedule: 'Save',
        cancelEdit: 'Cancel',
        deleteSchedule: 'Delete',
        days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        daysLong: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        from: 'From',
        to: 'To',
        repeat: 'Repeat',
        oneTime: 'One-time',
        label: 'Label',
        enabled: 'Enabled',
        disabled: 'Disabled',
        noSchedules: 'No scheduled privacy windows',
        noHistory: 'No history',
        historyTitle: 'Privacy history',
        started: 'Started',
        duration: 'Duration',
        min: 'min',
        manualPause: 'Manual pause',
        scheduled: 'Scheduled',
        cancelled: 'Cancelled',
        completed: 'Completed',
        errorCallScript: 'Error calling privacy script',
        errorStopAddon: 'Error stopping Frigate',
        errorStartAddon: 'Error starting Frigate',
        noCamerasFound: 'No Frigate cameras found',
        privacyModeStarted: 'Privacy mode started for',
        frigateResumed: 'Frigate resumed',
        tabSettings: 'Settings',
        notifications: 'Notifications',
        notifyEnabled: 'Enable notifications',
        notifyService: 'Notification service',
        notifyPersistent: 'HA notifications (persistent)',
        notifyMobile: 'Mobile app',
        notifyBeforeEnd: 'Notify before end (min)',
        extendTime: 'Extend time',
        extendBy: 'Extend by',
        privacyEndingSoon: 'Privacy ending in',
        forCameras: 'for cameras',
        allCamerasLabel: 'all cameras',
        notifExtendQuestion: 'Extend?',
        privacyExtended: 'Privacy extended by',
        scheduleReminder: 'Reminder: scheduled privacy',
        startsIn: 'starts in',
        endsIn: 'ends in',
      }
    };
    return T[this._lang] || T.en;
  }

  setConfig(config) {
    this._config = config;
    this._loadSchedules();
    this._loadHistory();
    this._loadNotifySettings();
    this._loadPrivacyState();
    this._updateUI();
  }

  set hass(hass) {
    if (hass?.language) this._lang = hass.language.startsWith('pl') ? 'pl' : 'en';
    this._hass = hass;
    if (!hass) return;
    const now = Date.now();
    // Update camera detection and status on EVERY hass update (not just once)
    // This ensures camera friendly_name changes are reflected, and status is always current
    this._detectCameras();
    this._checkFrigateSupport();
    this._updateFrigateStatus();

    if (!this._firstHassRender) {
      this._firstHassRender = true;
      // Check HA timer entity — authoritative server-side state
      const timerState = hass.states['timer.frigate_privacy'];
      if (timerState) {
        if (timerState.state === 'active' && !this._privacyActive) {
          // Timer running on server but card doesn't know — sync state
          const finishes = new Date(timerState.attributes.finishes_at).getTime();
          if (finishes > Date.now()) {
            this._privacyActive = true;
            this._privacyEndTime = finishes;
            this._startCountdown();
          }
        } else if (timerState.state === 'idle' && this._privacyActive) {
          // Timer finished server-side — clean up card state AND resume cameras
          const camsToResume = this._privacyCameras && this._privacyCameras !== 'all'
            ? this._privacyCameras.split(', ')
            : this._cameras.map(c => c.entity_id);
          this._privacyActive = false;
          this._privacyEndTime = null;
          this._savePrivacyState();
          if (this._privacyTimerInterval) { clearInterval(this._privacyTimerInterval); this._privacyTimerInterval = null; }
          this._setCameraStreams(camsToResume, true);
          this._addHistoryEntry('resumed', 0);
          const t = this._t;
          this._sendNotification('▶️ ' + t.frigateResumed + ' (auto)', t.forCameras + ': ' + (this._privacyCameras || 'all'));
        }
      }
      // Check if privacy timer expired while page was away
      if (this._pendingAddonRestart) {
        this._pendingAddonRestart = false;
        const camsRestart = this._privacyCameras && this._privacyCameras !== 'all'
          ? this._privacyCameras.split(', ')
          : this._cameras.map(c => c.entity_id);
        this._setCameraStreams(camsRestart, true);
        const t = this._t;
        this._sendNotification('\u25B6\uFE0F ' + t.frigateResumed + ' (auto)', t.forCameras + ': ' + (this._privacyCameras || 'all'));
        this._showToast(t.frigateResumed + ' (auto - timer expired)', 'success');
      }
      // Also check persisted state in case _loadPrivacyState found active+expired
      if (this._privacyActive && this._privacyEndTime && Date.now() >= this._privacyEndTime) {
        const camsExpired = this._privacyCameras && this._privacyCameras !== 'all'
          ? this._privacyCameras.split(', ')
          : this._cameras.map(c => c.entity_id);
        this._privacyActive = false;
        this._privacyEndTime = null;
        this._savePrivacyState();
        this._setCameraStreams(camsExpired, true);
        const t = this._t;
        this._sendNotification('\u25B6\uFE0F ' + t.frigateResumed + ' (auto)', t.forCameras + ': ' + (this._privacyCameras || 'all'));
      }
      this._updateUI();
      this._lastRenderTime = now;
      return;
    }
    if (now - (this._lastRenderTime || 0) < 5000) {
      if (!this._renderScheduled) {
        this._renderScheduled = true;
        setTimeout(() => {
          this._renderScheduled = false;
          // Check if privacy timer expired (handles case where user navigated away and back)
          if (this._privacyActive && this._privacyEndTime && Date.now() >= this._privacyEndTime && !this._privacyTimerInterval) {
            const camsDeferred = this._privacyCameras && this._privacyCameras !== 'all'
              ? this._privacyCameras.split(', ')
              : (this._cameras || []).map(c => c.entity_id);
            this._privacyActive = false;
            this._privacyEndTime = null;
            this._savePrivacyState();
            this._setCameraStreams(camsDeferred, true);
            const t = this._t;
            this._sendNotification('\u25B6\uFE0F ' + t.frigateResumed + ' (auto)', t.forCameras + ': ' + (this._privacyCameras || 'all'));
          }
          this._updateUI();
          this._lastRenderTime = Date.now();
        }, 5000 - (now - (this._lastRenderTime || 0)));
      }
      return;
    }
    // Auto-create HA helpers on first load
    if (!this._helpersChecked) this._ensureHAHelpers();
    // Check schedules every 60s
    if (now - this._lastScheduleCheck > 60000) {
      this._lastScheduleCheck = now;
      this._checkSchedules();
    }
    this._lastRenderTime = now;
    this._updateUI();
  }

  disconnectedCallback() {
    if (this._privacyTimerInterval) {
      clearInterval(this._privacyTimerInterval);
      this._privacyTimerInterval = null;
    }
  }

  _updateFrigateStatus() {
    if (!this._hass) return;
    // Check if Frigate is running by looking for detect switches or update entities
    const detectSwitches = Object.keys(this._hass.states).filter(id => id.startsWith('switch.') && id.endsWith('_detect'));
    if (detectSwitches.length > 0) {
      this._frigateRunning = true;
    } else {
      const frigateUpdate = this._hass.states['update.frigate_server'] || this._hass.states['update.frigate_update'] || this._hass.states['update.frigate_update_2'];
      this._frigateRunning = frigateUpdate ? true : null;
    }
  }

  async _checkAddonState() {
    try {
      const resp = await this._hass.callApi('GET', 'hassio/addons');
      if (resp && resp.data && resp.data.addons) {
        const frigateAddon = resp.data.addons.find(a =>
          (a.name || '').toLowerCase().includes('frigate') ||
          (a.slug || '').toLowerCase().includes('frigate')
        );
        if (frigateAddon) {
          this._frigateRunning = frigateAddon.state === 'started';
          this._updateUI();
          return;
        }
      }
    } catch (e) {
      // Supervisor API not available (e.g. non-supervised install)
    }
    this._frigateRunning = null;
    this._updateUI();
  }

  _detectCameras() {
    if (!this._hass) return;
    // Use config cameras if provided
    if (this._config.cameras && this._config.cameras.length > 0) {
      this._cameras = this._config.cameras.map(c => {
        const entity = this._hass.states[c];
        return {
          entity_id: c,
          name: entity ? (entity.attributes.friendly_name || c) : c
        };
      });
      return;
    }
    // Auto-detect: find cameras that have Frigate detect switches
    const allSwitches = Object.keys(this._hass.states).filter(id => id.startsWith('switch.') && id.endsWith('_detect'));
    const frigateCameraIds = [];
    Object.keys(this._hass.states).filter(id => id.startsWith('camera.')).forEach(camId => {
      const camName = camId.replace('camera.', '');
      if (allSwitches.some(sw => sw === 'switch.' + camName + '_detect')) {
        frigateCameraIds.push(camId);
      }
    });
    if (frigateCameraIds.length > 0) {
      this._cameras = frigateCameraIds.map(id => ({
        entity_id: id,
        name: this._hass.states[id].attributes.friendly_name || id
      }));
      return;
    }
    // Fallback: entity_id or entity_picture containing 'frigate'
    this._cameras = Object.keys(this._hass.states)
      .filter(id => id.startsWith('camera.') && (
        id.includes('frigate') ||
        (this._hass.states[id].attributes.entity_picture || '').includes('frigate')
      ))
      .map(id => ({
        entity_id: id,
        name: this._hass.states[id].attributes.friendly_name || id
      }));
    // Last resort: all cameras
    if (this._cameras.length === 0) {
      this._cameras = Object.keys(this._hass.states)
        .filter(id => id.startsWith('camera.'))
        .map(id => ({
          entity_id: id,
          name: this._hass.states[id].attributes.friendly_name || id
        }));
    }
  }

  // --- Frigate version check ---
  // Minimum supported Frigate version. Below 0.14 the per-camera switches
  // (_detect/_recordings/_snapshots/_motion/_enabled) don't exist as a stable
  // surface, so the privacy toggle cannot reliably disable the camera.
  // Frigate 0.17 dropped _enabled and renamed _audio → _audio_detection, and
  // added _review_alerts/_review_detections; the tool toggles the union of
  // both surfaces and skips entities that don't exist.
  static get MIN_FRIGATE_VERSION() { return { major: 0, minor: 14 }; }
  static get TESTED_FRIGATE_VERSION() { return '0.17.1'; }

  _parseFrigateVersion(raw) {
    if (!raw || typeof raw !== 'string') return null;
    const m = raw.match(/(\d+)\.(\d+)(?:\.(\d+))?/);
    if (!m) return null;
    return { major: parseInt(m[1]), minor: parseInt(m[2]), patch: parseInt(m[3] || '0'), raw: raw };
  }

  _detectFrigateVersion() {
    if (!this._hass) return null;
    // 1) update.* entity (most reliable — HA Frigate integration exposes one)
    const updateEntity = Object.keys(this._hass.states).find(id =>
      id.startsWith('update.') && id.includes('frigate')
    );
    if (updateEntity) {
      const attrs = this._hass.states[updateEntity].attributes || {};
      const v = this._parseFrigateVersion(attrs.installed_version || attrs.latest_version);
      if (v) return v;
    }
    // 2) sensor.frigate_* with version attribute
    for (const id of Object.keys(this._hass.states)) {
      if (!id.includes('frigate')) continue;
      const attrs = this._hass.states[id].attributes || {};
      const v = this._parseFrigateVersion(attrs.version || attrs.sw_version || attrs.installed_version);
      if (v) return v;
    }
    return null;
  }

  _checkFrigateSupport() {
    if (!this._hass) return { supported: true, reason: null };
    const t = this._t || {};
    const version = this._detectFrigateVersion();
    const min = this.constructor.MIN_FRIGATE_VERSION;
    const tested = this.constructor.TESTED_FRIGATE_VERSION;

    // Proxy check: does ANY detected camera have the _enabled master switch?
    const hasEnabledSwitch = (this._cameras || []).some(c => {
      const name = c.entity_id.replace('camera.', '');
      return !!this._hass.states['switch.' + name + '_enabled'];
    });

    let supported = true;
    let reason = null;

    if (version) {
      const tooOld = version.major < min.major ||
                     (version.major === min.major && version.minor < min.minor);
      if (tooOld) {
        supported = false;
        reason = 'Frigate ' + version.raw + ' nie jest wspierane. Minimum: ' +
                 min.major + '.' + min.minor + ' (testowane: ' + tested + '). ' +
                 'Brak master switcha switch.{name}_enabled \u2014 privacy toggle nie wy\u0142\u0105czy kamery w pe\u0142ni.';
      }
    } else if (!hasEnabledSwitch && (this._cameras || []).length > 0) {
      // Couldn't read version AND no _enabled switch found -> likely pre-0.14
      supported = false;
      reason = 'Nie wykryto wersji Frigate i \u017Cadna kamera nie ma switch.{name}_enabled. ' +
               'Wymagane Frigate ' + min.major + '.' + min.minor + '+ (testowane: ' + tested + ').';
    }

    this._frigateVersion = version;
    this._frigateSupported = supported;
    this._frigateUnsupportedReason = reason;

    if (!supported && !this._unsupportedWarningShown) {
      this._unsupportedWarningShown = true;
      console.error('[Frigate Privacy] ' + reason);
      try { this._showToast && this._showToast('\u26A0\uFE0F ' + reason, 'error'); } catch(_) { console.debug('[ha-frigate-privacy] caught:', e); }
      // Persistent notification so user sees it even if toast is missed
      try {
        this._hass.callService('persistent_notification', 'create', {
          notification_id: 'frigate_privacy_unsupported',
          title: '\u26A0\uFE0F Frigate Privacy \u2014 niewspierana wersja',
          message: reason + '\n\nZaktualizuj Frigate lub zmie\u0144 konfiguracj\u0119.'
        });
      } catch(_) { console.debug('[ha-frigate-privacy] caught:', e); }
    }
    return { supported: supported, reason: reason, version: version };
  }

  // --- Persistence via localStorage ---
  _storageKey(suffix) {
    return 'ha-frigate-privacy-' + suffix;
  }

  _loadSchedules() {
    try {
      const raw = localStorage.getItem(this._storageKey('schedules'));
      this._schedules = raw ? JSON.parse(raw) : [];
    } catch(e) { this._schedules = []; }
  }

  _saveSchedules() {
    try { localStorage.setItem(this._storageKey('schedules'), JSON.stringify(this._schedules)); } catch(e) { console.debug('[ha-frigate-privacy] caught:', e); }
    if (window._haToolsPersistence && this._hass) {
      window._haToolsPersistence.setHass(this._hass);
      window._haToolsPersistence.save('frigate-privacy-schedules', this._schedules).catch(() => {});
    }
  }

  _loadHistory() {
    try {
      const raw = localStorage.getItem(this._storageKey('history'));
      this._history = raw ? JSON.parse(raw) : [];
    } catch(e) { this._history = []; }
  }

  _saveHistory() {
    // Keep max 50 entries
    if (this._history.length > 50) this._history = this._history.slice(-50);
    try { localStorage.setItem(this._storageKey('history'), JSON.stringify(this._history)); } catch(e) { console.debug('[ha-frigate-privacy] caught:', e); }
    if (window._haToolsPersistence && this._hass) {
      window._haToolsPersistence.setHass(this._hass);
      window._haToolsPersistence.save('frigate-privacy-history', this._history).catch(() => {});
    }
  }

  _loadNotifySettings() {
    try {
      const raw = localStorage.getItem(this._storageKey('notify'));
      if (raw) {
        const s = JSON.parse(raw);
        this._notifyEnabled = s.enabled !== false;
        this._notifyService = s.service || 'persistent_notification';
        this._notifyBeforeEndMin = s.beforeEndMin || 5;
      }
    } catch(e) { /* defaults */ }
  }

  _saveNotifySettings() {
    const data = { enabled: this._notifyEnabled, service: this._notifyService, beforeEndMin: this._notifyBeforeEndMin };
    try { localStorage.setItem(this._storageKey('notify'), JSON.stringify(data)); } catch(e) { console.debug('[ha-frigate-privacy] caught:', e); }
    if (window._haToolsPersistence && this._hass) {
      window._haToolsPersistence.setHass(this._hass);
      window._haToolsPersistence.save('frigate-privacy-notify', data).catch(() => {});
    }
  }

  _savePrivacyState() {
    const data = (this._privacyActive && this._privacyEndTime) ? {
      active: true,
      endTime: this._privacyEndTime,
      cameras: this._privacyCameras || 'all',
      startedMin: this._privacyStartedMin || 0,
      addonId: this._config?.frigate_addon_id || 'ccab4aaf_frigate'
    } : null;
    // Save to both localStorage (fast) and HA server (cross-device)
    try { localStorage.setItem(this._storageKey('active'), data ? JSON.stringify(data) : ''); } catch(e) { console.debug('[ha-frigate-privacy] caught:', e); }
    if (window._haToolsPersistence && this._hass) {
      window._haToolsPersistence.setHass(this._hass);
      window._haToolsPersistence.save('frigate-privacy-active', data).catch(() => {});
    }
  }

  _loadPrivacyState() {
    // 1. Quick check from localStorage cache
    let s = null;
    try {
      const raw = localStorage.getItem(this._storageKey('active'));
      if (raw) s = JSON.parse(raw);
    } catch(e) { console.debug('[ha-frigate-privacy] caught:', e); }

    // 2. Also try server-side data (async, will update later)
    if (window._haToolsPersistence && this._hass) {
      window._haToolsPersistence.setHass(this._hass);
      window._haToolsPersistence.load('frigate-privacy-active').then(serverData => {
        if (serverData && serverData.active && serverData.endTime) {
          // Server data is newer/authoritative — use it
          this._applyPrivacyState(serverData);
        }
      }).catch(() => {});
    }

    // 3. Apply localStorage data immediately (sync)
    if (s && s.active && s.endTime) {
      this._applyPrivacyState(s);
    }
  }

  _applyPrivacyState(s) {
    if (!s || !s.active || !s.endTime) return;

    if (Date.now() >= s.endTime) {
      // Timer already expired while we were away
      console.info('[Frigate Privacy] Timer expired while away, will restart addon...');
      this._privacyActive = false;
      this._privacyEndTime = null;
      this._privacyCameras = s.cameras || 'all';
      this._savePrivacyState(); // Clear persisted state
      // Defer addon restart until hass is available
      this._pendingAddonRestart = true;
      this._addHistoryEntry('auto-resumed', 0, s.cameras);
    } else if (!this._privacyActive) {
      // Timer still active — resume countdown
      console.info('[Frigate Privacy] Resuming privacy timer, ' +
        Math.ceil((s.endTime - Date.now()) / 60000) + ' min remaining');
      this._privacyActive = true;
      this._privacyEndTime = s.endTime;
      this._privacyCameras = s.cameras || 'all';
      this._privacyStartedMin = s.startedMin || 0;
      this._warningSent = false;
      this._startCountdown();
    }
  }



  async _sendNotification(title, message) {
    if (!this._notifyEnabled || !this._hass) return;
    try {
      if (this._notifyService === 'persistent_notification') {
        await this._hass.callService('persistent_notification', 'create', {
          title: title,
          message: message
        });
      } else {
        // Mobile app notify service (e.g. notify.mobile_app_iphone)
        const [domain, service] = this._notifyService.includes('.') ?
          this._notifyService.split('.', 2) : ['notify', this._notifyService];
        await this._hass.callService(domain, service, {
          title: title,
          message: message
        });
      }
    } catch(e) {
      console.warn('[Frigate Privacy] Notification error:', e);
    }
  }

  _getCameraLabel() {
    if (!this._privacyCameras || this._privacyCameras === 'all') {
      return this._t.allCamerasLabel;
    }
    return this._privacyCameras;
  }

  async _extendPrivacy(extraMinutes) {
    const t = this._t;
    if (!this._hass || !this._privacyActive) return;
    // Extend the end time
    this._privacyEndTime += extraMinutes * 60 * 1000;
    this._privacyStartedMin += extraMinutes;
    this._warningSent = false; // Reset so we get another warning
    this._savePrivacyState();
    this._addHistoryEntry('extended', extraMinutes, this._privacyCameras);
    this._showToast(t.privacyExtended + ' ' + extraMinutes + ' ' + t.min, 'success');
    // JS timer handles extension - addon is already stopped
    const remaining = Math.ceil((this._privacyEndTime - Date.now()) / 60000);
    this._sendNotification(
      '\uD83D\uDD12 ' + t.privacyExtended + ' ' + extraMinutes + t.min,
      t.forCameras + ': ' + this._getCameraLabel() + '. ' + t.remainingTime + ': ' + remaining + ' ' + t.min
    );
    this._updateUI();
  }

  _addHistoryEntry(type, minutes, cameras) {
    this._history.push({
      ts: Date.now(),
      type: type, // 'manual' | 'scheduled' | 'cancelled' | 'resumed'
      minutes: minutes,
      cameras: cameras || 'all'
    });
    this._saveHistory();
  }

  // --- HA server-side helpers management ---
  async _syncCamerasToHA(camerasStr) {
    if (!this._hass) return;
    try {
      if (this._hass.states['input_text.frigate_privacy_cameras']) {
        await this._hass.callService('input_text', 'set_value', {
          entity_id: 'input_text.frigate_privacy_cameras',
          value: (camerasStr || '').substring(0, 255)
        });
      }
    } catch(e) { console.warn('[Frigate Privacy] Could not sync cameras to HA:', e); }
  }

  async _ensureHAHelpers() {
    if (!this._hass || this._helpersChecked) return;
    this._helpersChecked = true;
    // Auto-create timer.frigate_privacy if missing
    if (!this._hass.states['timer.frigate_privacy']) {
      try {
        await this._hass.callWS({ type: 'timer/create', name: 'Frigate Privacy', icon: 'mdi:camera-timer', duration: '01:00:00' });
        console.info('[Frigate Privacy] Created timer.frigate_privacy helper');
      } catch(e) { console.warn('[Frigate Privacy] Could not auto-create timer helper:', e); }
    }
    // Auto-create input_text.frigate_privacy_cameras if missing
    if (!this._hass.states['input_text.frigate_privacy_cameras']) {
      try {
        await this._hass.callWS({ type: 'input_text/create', name: 'Frigate Privacy Cameras', icon: 'mdi:camera-off', min: 0, max: 255, mode: 'text' });
        console.info('[Frigate Privacy] Created input_text.frigate_privacy_cameras helper');
      } catch(e) { console.warn('[Frigate Privacy] Could not auto-create input_text helper:', e); }
    }
    // Auto-create/update the timer expiry automation (server-side camera resume)
    // This is critical: when timer expires and browser is closed, HA must turn cameras back on
    await this._ensureTimerExpiryAutomation();
  }

  async _ensureTimerExpiryAutomation() {
    if (!this._hass) return;
    // Detect all Frigate camera switches dynamically (version-aware: includes
    // _audio_detection / _review_alerts / _review_detections on Frigate 0.17+,
    // _enabled / _audio on 0.14-0.16). Critical for HACS users — the auto-resume
    // automation must cover EVERY switch the tool toggles off, otherwise privacy
    // leaks audio/review processing back on after timer expires with browser closed.
    const allSwitches = this._getAllFrigateSwitchesForKnownCameras();
    if (allSwitches.length === 0) return; // No Frigate switches found — skip

    // Resolve the storage id to write to:
    //  - If an automation with our expected entity_id already exists (whether we
    //    created it before, or the user created it manually with that alias), reuse
    //    its internal id so we update in place instead of creating a duplicate.
    //  - Otherwise use a stable id so subsequent loads update the same record.
    const expectedEntityId = 'automation.frigate_privacy_resume_cameras_when_timer_expires';
    const existing = this._hass.states[expectedEntityId];
    const configId = (existing && existing.attributes && existing.attributes.id)
      ? existing.attributes.id
      : 'ha_tools_frigate_privacy_resume';

    // Build the automation config (modern HA syntax: triggers/conditions/actions plural)
    const config = {
      alias: 'Frigate Privacy - Resume cameras when timer expires',
      description: 'Auto-generated by ha-tools (Frigate ' + (this._frigateVersion?.raw || 'unknown') + ', ' + allSwitches.length + ' switches). Turns on every Frigate camera switch when privacy timer finishes. Works even with browser closed.',
      mode: 'single',
      triggers: [{ trigger: 'event', event_type: 'timer.finished', event_data: { entity_id: 'timer.frigate_privacy' } }],
      conditions: [],
      actions: [
        { action: 'switch.turn_on', target: { entity_id: allSwitches } }
      ]
    };
    // Add input_text clear if helper exists
    if (this._hass.states['input_text.frigate_privacy_cameras']) {
      config.actions.push({ action: 'input_text.set_value', target: { entity_id: 'input_text.frigate_privacy_cameras' }, data: { value: '' } });
    }
    config.actions.push({ action: 'persistent_notification.create', data: { title: '\u25B6\uFE0F Frigate Privacy', message: 'Privacy timer expired. All camera switches resumed automatically.' } });

    try {
      const r = await fetch('/api/config/automation/config/' + encodeURIComponent(configId), {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + this._hass.auth.data.access_token,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
      });
      if (!r.ok) {
        const body = await r.text();
        console.warn('[Frigate Privacy] Save timer-expiry automation failed: HTTP ' + r.status + ' ' + body);
        return;
      }
      // Reload automations so the new/updated config is live (REST write doesn't auto-reload).
      try { await this._hass.callService('automation', 'reload', {}); } catch(_) { /* not critical */ }
      console.info('[Frigate Privacy] Ensured timer expiry automation (id=' + configId + ', ' + allSwitches.length + ' switches, Frigate ' + (this._frigateVersion?.raw || 'unknown') + ')');
    } catch(e) {
      console.warn('[Frigate Privacy] Could not create timer expiry automation:', e);
    }
  }

  // --- Schedule execution (checks every 60s in set hass) ---
  _checkSchedules() {
    if (!this._hass || !this._schedules || this._schedules.length === 0) return;
    const now = new Date();
    const dayOfWeek = now.getDay() === 0 ? 7 : now.getDay(); // 1=Mon..7=Sun
    const nowMin = now.getHours() * 60 + now.getMinutes();

    for (const sched of this._schedules) {
      if (!sched.enabled) continue;
      if (!sched.days.includes(dayOfWeek)) continue;
      const startMin = sched.startHour * 60 + (sched.startMin || 0);
      const endMin = sched.endHour * 60 + (sched.endMin || 0);
      const inWindow = endMin > startMin
        ? (nowMin >= startMin && nowMin < endMin)
        : (nowMin >= startMin || nowMin < endMin); // overnight

      if (inWindow && !this._privacyActive) {
        // Schedule should be active but privacy is off — start it
        const durationMin = endMin > startMin ? (endMin - nowMin) : (1440 - nowMin + endMin);
        console.info('[Frigate Privacy] Schedule triggered: ' + (sched.label || 'unnamed') + ', duration: ' + durationMin + 'min');
        this._pauseFrigate(Math.max(1, durationMin));
        this._addHistoryEntry('scheduled', durationMin, this._privacyCameras);
        return; // only one schedule at a time
      }
    }
  }

  async _syncScheduleToHA(sched, idx, remove) {
    if (!this._hass) return;
    const automationId = 'frigate_privacy_schedule_' + idx;
    if (remove || !sched || !sched.enabled) {
      // Remove HA automation if it exists
      try {
        const existing = this._hass.states['automation.' + automationId];
        if (existing) {
          await this._hass.callService('automation', 'turn_off', { entity_id: 'automation.' + automationId });
        }
      } catch(e) { console.debug('[ha-frigate-privacy] caught:', e); }
      return;
    }
    // Create/update HA automation for this schedule
    const dayMap = { 1: 'mon', 2: 'tue', 3: 'wed', 4: 'thu', 5: 'fri', 6: 'sat', 7: 'sun' };
    const weekdays = sched.days.map(d => dayMap[d]).filter(Boolean);
    const startTime = String(sched.startHour).padStart(2, '0') + ':' + String(sched.startMin || 0).padStart(2, '0') + ':00';
    const endTime = String(sched.endHour).padStart(2, '0') + ':' + String(sched.endMin || 0).padStart(2, '0') + ':00';
    const durationMin = (sched.endHour * 60 + (sched.endMin || 0)) - (sched.startHour * 60 + (sched.startMin || 0));
    const durationMinAbs = durationMin > 0 ? durationMin : durationMin + 1440;
    const durationH = Math.floor(durationMinAbs / 60);
    const durationM = durationMinAbs % 60;
    const durStr = String(durationH).padStart(2, '0') + ':' + String(durationM).padStart(2, '0') + ':00';

    // Get all camera switches (version-aware — covers 0.14-0.17 surface,
    // so the schedule automation pauses every relevant feature switch).
    const switches = this._getAllFrigateSwitchesForKnownCameras();

    // Build actions
    const actions = [
      { action: 'switch.turn_off', target: { entity_id: switches } },
      { action: 'timer.start', target: { entity_id: 'timer.frigate_privacy' }, data: { duration: durStr } }
    ];
    if (this._hass.states['input_text.frigate_privacy_cameras']) {
      actions.push({ action: 'input_text.set_value', target: { entity_id: 'input_text.frigate_privacy_cameras' }, data: { value: 'all (schedule)' } });
    }
    actions.push({ action: 'persistent_notification.create', data: { title: '\uD83D\uDD12 Frigate Privacy (schedule)', message: (sched.label || 'Schedule #' + idx) + ' activated. Cameras paused for ' + durationMinAbs + ' min.' } });

    const config = {
      alias: 'Frigate Privacy Schedule: ' + (sched.label || '#' + idx),
      description: 'Auto-generated by ha-tools Frigate Privacy (Frigate ' + (this._frigateVersion?.raw || 'unknown') + ', ' + switches.length + ' switches). Pauses cameras on schedule.',
      mode: 'single',
      triggers: [{ trigger: 'time', at: startTime }],
      conditions: [{ condition: 'time', weekday: weekdays }],
      actions
    };

    // Use stable internal id so subsequent saves update the same record.
    // Reuse existing internal id if entity already exists (handles users who
    // first created the schedule manually with a different id).
    const expectedEntityId = 'automation.' + automationId;
    const existingEnt = this._hass.states[expectedEntityId];
    const configId = (existingEnt && existingEnt.attributes && existingEnt.attributes.id)
      ? existingEnt.attributes.id
      : 'ha_tools_' + automationId;

    try {
      const r = await fetch('/api/config/automation/config/' + encodeURIComponent(configId), {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + this._hass.auth.data.access_token,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
      });
      if (!r.ok) {
        const body = await r.text();
        console.warn('[Frigate Privacy] Save schedule automation failed: HTTP ' + r.status + ' ' + body);
        return;
      }
      try { await this._hass.callService('automation', 'reload', {}); } catch(_) { /* not critical */ }
      console.info('[Frigate Privacy] Synced schedule automation: id=' + configId + ', ' + switches.length + ' switches');
    } catch(e) { console.warn('[Frigate Privacy] Could not sync schedule automation:', e); }
  }

  // --- Frigate switch surface (version-aware) ---
  // Returns the list of switch suffixes that exist on the detected Frigate version.
  // 0.17+: dropped switch.{name}_enabled and renamed _audio → _audio_detection,
  //        added _review_alerts / _review_detections.
  // 0.14-0.16: master _enabled + per-feature switches (older _audio name).
  // Unknown version: union of both surfaces — the per-id existence check filters
  // out entities that don't exist, so this is safe (just a few wasted state lookups).
  // This makes the tool work out-of-the-box for HACS users on any supported Frigate.
  _getFrigateSwitchSuffixes() {
    const v = this._frigateVersion;
    if (v && (v.major > 0 || v.minor >= 17)) {
      return ['_detect', '_recordings', '_snapshots', '_motion', '_audio_detection', '_review_alerts', '_review_detections'];
    }
    if (v && v.major === 0 && v.minor >= 14) {
      // _enabled first: single atomic call disables the whole camera in Frigate 0.14-0.16.
      return ['_enabled', '_detect', '_recordings', '_snapshots', '_motion', '_audio'];
    }
    // No version detected — try the union and let exists-check filter.
    return ['_enabled', '_detect', '_recordings', '_snapshots', '_motion', '_audio', '_audio_detection', '_review_alerts', '_review_detections'];
  }

  // Returns all Frigate switch entity_ids belonging to detected cameras + version-appropriate suffixes.
  // Used when building auto-managed HA automations (timer expiry, schedules) so the entity list
  // always matches the user's actual setup without manual YAML editing.
  _getAllFrigateSwitchesForKnownCameras() {
    if (!this._hass || !this._cameras) return [];
    const suffixes = this._getFrigateSwitchSuffixes();
    const out = [];
    for (const cam of this._cameras) {
      const name = cam.entity_id.replace('camera.', '');
      for (const s of suffixes) {
        const id = 'switch.' + name + s;
        if (this._hass.states[id]) out.push(id);
      }
    }
    return out;
  }

  // --- Camera stream control helper ---
  async _setCameraStreams(camIds, turnOn) {
    if (!this._hass) return;
    // NOTE: We intentionally do NOT call camera.turn_off/turn_on.
    // Turning off the camera entity stops the entire Frigate camera pipeline,
    // which can cause Google Coral TPU to be released. On turn_on, Frigate may
    // fail to re-acquire the Coral (USB race condition) and fall back to CPU.
    // Instead, we only toggle the per-feature Frigate switches, which pauses
    // processing without stopping the camera stream or releasing the TPU.
    const switchAction = turnOn ? 'turn_on' : 'turn_off';
    const suffixes = this._getFrigateSwitchSuffixes();
    let toggledCount = 0;
    const missingPerCam = [];
    for (const camId of camIds) {
      const camName = camId.replace('camera.', '');
      let camToggled = 0;
      for (const suffix of suffixes) {
        const switchId = 'switch.' + camName + suffix;
        if (this._hass.states[switchId]) {
          try {
            await this._hass.callService('switch', switchAction, { entity_id: switchId });
            camToggled++;
            toggledCount++;
          } catch(e) {
            console.warn('[Frigate Privacy] switch.' + switchAction + ' failed for ' + switchId + ':', e.message || e);
          }
        }
      }
      if (camToggled === 0) missingPerCam.push(camId);
    }
    const verLabel = this._frigateVersion ? this._frigateVersion.raw : 'unknown';
    if (toggledCount === 0) {
      console.error('[Frigate Privacy] No Frigate switches found for cameras: ' + camIds.join(', ') +
        ' (Frigate ' + verLabel + '). Expected suffixes: ' + suffixes.join(', ') + '. Check entity naming.');
      try { this._showToast && this._showToast('Frigate Privacy: nie znaleziono switchy dla kamer (' + camIds.join(', ') + ')', 'error'); } catch(_) { console.debug('[ha-frigate-privacy] caught:', _); }
    } else if (missingPerCam.length) {
      console.warn('[Frigate Privacy] No switches found for: ' + missingPerCam.join(', '));
    } else {
      console.info('[Frigate Privacy] Toggled ' + toggledCount + ' switches (' + switchAction + ') for ' + camIds.length + ' camera(s) on Frigate ' + verLabel);
    }
  }

  // --- Actions ---
  async _pauseFrigate(minutes) {
    const t = this._t;
    if (!this._hass) return;
    // Guard: block pause if Frigate version is unsupported — otherwise privacy
    // toggle gives false sense of security (camera keeps working silently).
    if (this._frigateSupported === false) {
      const msg = this._frigateUnsupportedReason || 'Niewspierana wersja Frigate';
      console.error('[Frigate Privacy] Pause blocked: ' + msg);
      try { this._showToast && this._showToast('\u26A0\uFE0F ' + msg, 'error'); } catch(_) { console.debug('[ha-frigate-privacy] caught:', e); }
      return;
    }
    const addonId = this._config.frigate_addon_id || 'ccab4aaf_frigate';
    try {
      // Pause selected cameras
      const selectedCams = this._selectedCameras.size > 0 ? [...this._selectedCameras] : this._cameras.map(c => c.entity_id);
      await this._setCameraStreams(selectedCams, false);
      this._privacyActive = true;
      this._privacyEndTime = Date.now() + (parseInt(minutes) * 60 * 1000);
      this._privacyCameras = selectedCams.join(', ');
      this._privacyStartedMin = parseInt(minutes);
      this._warningSent = false;
      this._addHistoryEntry('manual', minutes, this._privacyCameras);
      this._savePrivacyState();
      // Start HA server-side timer (survives page close, works across devices)
      try {
        const hrs = Math.floor(parseInt(minutes) / 60);
        const mins = parseInt(minutes) % 60;
        const dur = String(hrs).padStart(2,'0') + ':' + String(mins).padStart(2,'0') + ':00';
        await this._hass.callService('timer', 'start', { entity_id: 'timer.frigate_privacy', duration: dur });
      } catch(e) { console.warn('[Frigate Privacy] Could not start HA timer:', e); }
      // Sync paused cameras to HA entity (survives browser close)
      this._syncCamerasToHA(selectedCams.join(', '));
      this._startCountdown();
      this._showToast(t.privacyModeStarted + ' ' + minutes + ' ' + t.min, 'success');
      this._sendNotification(
        '\uD83D\uDD12 ' + t.privacyModeStarted + ' ' + minutes + ' ' + t.min,
        t.forCameras + ': ' + this._getCameraLabel()
      );
      this._updateUI();
    } catch(e) {
      console.warn('[Frigate Privacy]', e);
      this._showToast(t.errorStopAddon, 'error');
    }
  }

  async _resumeFrigate() {
    const t = this._t;
    if (!this._hass) return;
    const addonId = this._config.frigate_addon_id || 'ccab4aaf_frigate';
    try {
      // Resume cameras
      const camsToResume = this._privacyCameras && this._privacyCameras !== 'all'
        ? this._privacyCameras.split(', ')
        : this._cameras.map(c => c.entity_id);
      await this._setCameraStreams(camsToResume, true);
      this._privacyActive = false;
      this._privacyEndTime = null;
      if (this._privacyTimerInterval) {
        clearInterval(this._privacyTimerInterval);
        this._privacyTimerInterval = null;
      }
      this._savePrivacyState();
      // Clear paused cameras in HA entity
      this._syncCamerasToHA('');
      // Cancel HA server-side timer
      try {
        await this._hass.callService('timer', 'cancel', { entity_id: 'timer.frigate_privacy' });
      } catch(e) { console.warn('[Frigate Privacy] Could not cancel HA timer:', e); }
      this._addHistoryEntry('cancelled', 0);
      this._warningSent = false;
      this._showToast(t.frigateResumed, 'success');
      this._sendNotification('\u25B6\uFE0F ' + t.frigateResumed, t.forCameras + ': ' + this._getCameraLabel());
      this._updateUI();
    } catch(e) {
      console.warn('[Frigate Privacy]', e);
      this._showToast(t.errorStartAddon, 'error');
    }
  }

  _startCountdown() {
    if (this._privacyTimerInterval) clearInterval(this._privacyTimerInterval);
    this._privacyTimerInterval = setInterval(() => {
      if (!this._privacyEndTime || Date.now() >= this._privacyEndTime) {
        // Timer expired - auto-restart Frigate addon
        this._privacyActive = false;
        this._privacyEndTime = null;
        this._savePrivacyState(); // Clear persisted state
        clearInterval(this._privacyTimerInterval);
        this._privacyTimerInterval = null;
        this._warningSent = false;
        // Auto-resume cameras: turn streams + switches back ON
        if (this._hass) {
          const camsToResume = this._privacyCameras && this._privacyCameras !== 'all'
            ? this._privacyCameras.split(', ')
            : this._cameras.map(c => c.entity_id);
          this._setCameraStreams(camsToResume, true);
          const t = this._t;
          this._addHistoryEntry('resumed', 0);
          this._sendNotification('\u25B6\uFE0F ' + t.frigateResumed, t.forCameras + ': ' + this._getCameraLabel());
        }
      } else {
        // Send warning notification before end
        const remainMs = this._privacyEndTime - Date.now();
        const warnMs = this._notifyBeforeEndMin * 60 * 1000;
        if (!this._warningSent && remainMs <= warnMs && remainMs > 0) {
          this._warningSent = true;
          const t = this._t;
          const mins = Math.ceil(remainMs / 60000);
          this._sendNotification(
            '\u23F3 ' + t.privacyEndingSoon + ' ' + mins + ' ' + t.min,
            t.forCameras + ': ' + this._getCameraLabel() + '. ' + t.notifExtendQuestion
          );
        }
      }
      this._updateCountdownDisplay();
    }, 1000);
  }

  _updateCountdownDisplay() {
    const el = this.shadowRoot?.querySelector('.countdown-value');
    if (!el) return;
    if (!this._privacyEndTime) {
      el.textContent = '--:--';
      return;
    }
    const remaining = Math.max(0, this._privacyEndTime - Date.now());
    const mins = Math.floor(remaining / 60000);
    const secs = Math.floor((remaining % 60000) / 1000);
    el.textContent = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
    if (remaining <= 0) {
      this._privacyActive = false;
      this._updateUI();
    }
  }

  _showToast(msg, type) {
    const toast = this.shadowRoot?.querySelector('.toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.className = 'toast toast-' + (type || 'info') + ' toast-show';
    setTimeout(() => { toast.className = 'toast'; }, 3000);
  }

  // --- Schedule management ---
  _resetScheduleForm() {
    this._scheduleForm = { enabled: true, days: [1,2,3,4,5], startHour: 18, startMin: 0, endHour: 20, endMin: 0, repeat: true, label: '' };
    this._editingScheduleIdx = null;
  }

  _saveScheduleFromForm() {
    const f = this._scheduleForm;
    const schedule = {
      enabled: f.enabled,
      days: [...f.days],
      startHour: parseInt(f.startHour),
      startMin: parseInt(f.startMin),
      endHour: parseInt(f.endHour),
      endMin: parseInt(f.endMin),
      repeat: f.repeat,
      label: f.label || ''
    };
    if (this._editingScheduleIdx !== null) {
      this._schedules[this._editingScheduleIdx] = schedule;
    } else {
      this._schedules.push(schedule);
    }
    this._saveSchedules();
    const savedIdx = this._editingScheduleIdx !== null ? this._editingScheduleIdx : this._schedules.length - 1;
    this._syncScheduleToHA(schedule, savedIdx, false);
    this._resetScheduleForm();
    this._updateUI();
  }

  _deleteSchedule(idx) {
    this._syncScheduleToHA(null, idx, true);
    this._schedules.splice(idx, 1);
    this._saveSchedules();
    // Re-sync remaining schedules (indices shifted)
    this._schedules.forEach((s, i) => this._syncScheduleToHA(s, i, false));
    this._updateUI();
  }

  _editSchedule(idx) {
    const s = this._schedules[idx];
    this._scheduleForm = { ...s, days: [...s.days] };
    this._editingScheduleIdx = idx;
    this._activeTab = 'schedule';
    this._updateUI();
    // Scroll to form
    setTimeout(() => {
      const form = this.shadowRoot?.querySelector('.schedule-form');
      if (form) form.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  }

  _toggleScheduleEnabled(idx) {
    this._schedules[idx].enabled = !this._schedules[idx].enabled;
    this._saveSchedules();
    this._syncScheduleToHA(this._schedules[idx], idx, false);
    this._updateUI();
  }

  // --- UI ---
  _updateUI() {
    const t = this._t;
    const html = this._buildHTML();
    if (html === this._lastHtml) return;
    this._lastHtml = html;
    this.shadowRoot.innerHTML = html;
    this._attachEvents();
    if (this._privacyActive) this._updateCountdownDisplay();
  }

  _buildHTML() {
    const t = this._t;
    return `<style>${window.HAToolsBentoCSS || ''}
/* === Support / Donation Section (HA Tools split) === */
.donate-section { margin: 20px 0 4px; padding: 18px 20px;  background: var(--donate-bg, linear-gradient(135deg, #fff5f5 0%, #fff0f6 50%, #f8f0ff 100%));  border: 1px solid var(--donate-border, #f3d3e0); border-radius: var(--bento-radius-md, 16px);  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; }
.donate-section h3 { margin: 0 0 6px; font-size: 15px; color: var(--donate-heading, #be185d); }
.donate-section p  { margin: 0; font-size: 12.5px; line-height: 1.55; color: var(--donate-text, #6b21a8); }
.donate-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
.donate-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 10px;  font-weight: 600; font-size: 12.5px; text-decoration: none; transition: transform .15s ease, box-shadow .15s ease; }
.donate-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 10px rgba(0,0,0,0.08); }
.donate-btn.coffee { background: #FFDD00; color: #000; border: 1px solid #e6c700; }
.donate-btn.paypal { background: #0070ba; color: #fff; border: 1px solid #005ea6; }
@media (prefers-color-scheme: dark) {  .donate-section { background: linear-gradient(135deg, #2a1525 0%, #1e1530 50%, #251530 100%); border-color: #4a3555; }  .donate-section h3 { color: #f0c0d8; }  .donate-section p  { color: #d4a0b8; }  .donate-btn.coffee { background: #b8a100; color: #fff; border-color: #8a7a00; }  .donate-btn.paypal { background: #005a96; color: #e0f0ff; border-color: #004a7a; } }
@media (max-width: 600px) {  .donate-section { flex-direction: column; text-align: center; padding: 16px; }  .donate-buttons { justify-content: center; } }
</style><style>${this._getCSS()}</style>
    <div class="card">
      <div class="header">
        <div class="header-left">
          <span class="header-icon">\uD83D\uDD12</span>
          <h2>${t.title}</h2>
        </div>
        <div class="status-badge ${this._frigateRunning === true ? 'status-running' : this._frigateRunning === false ? 'status-stopped' : 'status-unknown'}">
          <span class="status-dot"></span>
          ${this._frigateRunning === true ? t.running : this._frigateRunning === false ? t.stopped : t.unknown}
        </div>
      </div>

      <div class="tabs" role="tablist">
        <button class="tab-btn ${this._activeTab === 'control' ? 'active' : ''}" data-tab="control" role="tab" aria-selected="${!!(this._activeTab === 'control' )}">${t.tabControl}</button>
        <button class="tab-btn ${this._activeTab === 'schedule' ? 'active' : ''}" data-tab="schedule" role="tab" aria-selected="${!!(this._activeTab === 'schedule' )}">${t.tabSchedule}</button>
        <button class="tab-btn ${this._activeTab === 'history' ? 'active' : ''}" data-tab="history" role="tab" aria-selected="${!!(this._activeTab === 'history' )}">${t.tabHistory}</button>
        <button class="tab-btn ${this._activeTab === 'settings' ? 'active' : ''}" data-tab="settings" role="tab" aria-selected="${!!(this._activeTab === 'settings' )}">${t.tabSettings}</button>
      </div>

      <div class="tab-content">
        ${this._activeTab === 'control' ? this._buildControlTab() : ''}
        ${this._activeTab === 'schedule' ? this._buildScheduleTab() : ''}
        ${this._activeTab === 'history' ? this._buildHistoryTab() : ''}
        ${this._activeTab === 'settings' ? this._buildSettingsTab() : ''}
      </div>

      <div class="toast"></div>
    
        <!-- Support / Donation -->
        <div class="donate-section" data-source="ha-tools-split">
          <div class="donate-text">
            <h3>❤️ ${this._lang === 'pl' ? 'Wesprzyj rozwój HA Tools' : 'Support HA Tools Development'}</h3>
            <p>${this._lang === 'pl' ? 'Jeśli to narzędzie ułatwia Ci życie z Home Assistant, rozważ wsparcie projektu. Każda kawa motywuje do dalszego rozwoju!' : 'If this tool makes your Home Assistant life easier, consider supporting the project. Every coffee motivates further development!'}</p>
          </div>
          <div class="donate-buttons">
            <a class="donate-btn coffee" href="https://buymeacoffee.com/macsiem" target="_blank" rel="noopener noreferrer">☕ Buy Me a Coffee</a>
            <a class="donate-btn paypal" href="https://www.paypal.com/donate/?hosted_button_id=Y967H4PLRBN8W" target="_blank" rel="noopener noreferrer">💳 PayPal</a>
          </div>
        </div>
        </div>`;
  }

  _buildControlTab() {
    const t = this._t;

    // Privacy active banner
    let privacyBanner = '';
    if (this._privacyActive) {
      const camLabel = this._getCameraLabel();
      privacyBanner = `
        <div class="privacy-active-banner">
          <div class="privacy-icon">\uD83D\uDD12</div>
          <div class="privacy-info">
            <div class="privacy-label">${t.privacyActive}</div>
            <div class="privacy-cameras-label">${t.forCameras}: ${_esc(camLabel)}</div>
            <div class="countdown">
              <span class="countdown-label">${t.remainingTime}:</span>
              <span class="countdown-value">--:--</span>
            </div>
          </div>
          <div class="privacy-banner-actions">
            <div class="extend-row">
              <span class="extend-label">${t.extendBy}:</span>
              <button class="btn btn-extend" data-extend="15">+15m</button>
              <button class="btn btn-extend" data-extend="30">+30m</button>
              <button class="btn btn-extend" data-extend="60">+1h</button>
            </div>
            <button class="btn btn-danger btn-cancel" data-action="resume">${t.cancelPrivacy}</button>
          </div>
        </div>`;
    }

    // Camera selector
    const cameraCards = this._cameras.map(cam => {
      const selected = this._selectedCameras.has(cam.entity_id);
      const state = this._hass?.states[cam.entity_id];
      const statusIcon = state?.state === 'idle' || state?.state === 'streaming' ? '\uD83D\uDFE2' : '\u26AA';
      return `<div class="camera-card ${selected ? 'selected' : ''}" data-camera="${cam.entity_id}" role="button" tabindex="0" aria-pressed="${!!selected}" aria-label="Camera: ${this._sanitize(cam.name)}">
        <span class="camera-status" aria-hidden="true">${statusIcon}</span>
        <span class="camera-name">${this._sanitize(cam.name)}</span>
        <span class="camera-check" aria-hidden="true">${selected ? '\u2713' : ''}</span>
      </div>`;
    }).join('');

    const allSelected = this._selectedCameras.size === 0;

    // Quick pause buttons
    const quickButtons = [15, 30, 60, 120].map(m => {
      const label = m >= 60 ? (m / 60) + 'h' : m + 'min';
      return `<button class="btn btn-quick" data-minutes="${m}" aria-label="Pause for ${label}">${label}</button>`;
    }).join('');

    return `
      ${privacyBanner}

      <div class="section">
        <h3>${t.selectCameras}</h3>
        <div class="camera-grid">
          <div class="camera-card all-cameras ${allSelected ? 'selected' : ''}" data-camera="__all__" role="button" tabindex="0" aria-pressed="${!!allSelected}" aria-label="${t.allCameras}">
            <span class="camera-status" aria-hidden="true">\uD83C\uDFA5</span>
            <span class="camera-name">${t.allCameras}</span>
            <span class="camera-check" aria-hidden="true">${allSelected ? '\u2713' : ''}</span>
          </div>
          ${cameraCards}
        </div>
      </div>

      <div class="section">
        <h3>${t.quickPause}</h3>
        <div class="quick-buttons">
          ${quickButtons}
        </div>
      </div>

      <div class="section">
        <h3>${t.customDuration}</h3>
        <div class="custom-pause">
          <input type="number" class="input-minutes" min="1" max="1440" value="${this._customMinutes}" />
          <span class="input-suffix">${t.min}</span>
          <button class="btn btn-primary btn-pause" data-action="pause-custom" ${this._privacyActive ? 'disabled' : ''}>
            ${t.pauseFrigate}
          </button>
        </div>
      </div>

      ${!this._privacyActive && this._frigateRunning === false ? `
      <div class="section">
        <button class="btn btn-success btn-full" data-action="resume">${t.resumeFrigate}</button>
      </div>
      ` : ''}
    `;
  }

  _buildScheduleTab() {
    const t = this._t;
    const isEditing = this._editingScheduleIdx !== null;

    // Schedule list
    let scheduleList = '';
    if (this._schedules.length === 0) {
      scheduleList = `<div class="empty-state">${t.noSchedules}</div>`;
    } else {
      scheduleList = this._schedules.map((s, i) => {
        const dayLabels = s.days.sort().map(d => t.days[d - 1]).join(', ');
        const timeRange = String(s.startHour).padStart(2, '0') + ':' + String(s.startMin).padStart(2, '0')
          + ' - ' + String(s.endHour).padStart(2, '0') + ':' + String(s.endMin).padStart(2, '0');
        return `<div class="schedule-item ${s.enabled ? '' : 'disabled'}">
          <div class="schedule-main">
            <div class="schedule-label">${_esc(s.label) || (s.repeat ? t.repeat : t.oneTime)}</div>
            <div class="schedule-time">${timeRange}</div>
            <div class="schedule-days">${dayLabels}</div>
          </div>
          <div class="schedule-actions">
            <button class="btn-icon" data-schedule-toggle="${i}" title="${s.enabled ? t.enabled : t.disabled}" aria-label="${s.enabled ? t.enabled : t.disabled}">
              ${s.enabled ? '\uD83D\uDFE2' : '\u26AA'}
            </button>
            <button class="btn-icon" data-schedule-edit="${i}" title="${t.editSchedule}" aria-label="${t.editSchedule}">\u270F\uFE0F</button>
            <button class="btn-icon btn-icon-danger" data-schedule-delete="${i}" title="${t.deleteSchedule}" aria-label="${t.deleteSchedule}">\uD83D\uDDD1\uFE0F</button>
          </div>
        </div>`;
      }).join('');
    }

    // Schedule form
    const f = this._scheduleForm;
    const dayButtons = [1,2,3,4,5,6,7].map(d => {
      const active = f.days.includes(d);
      return `<button class="day-btn ${active ? 'active' : ''}" data-day="${d}">${t.days[d-1]}</button>`;
    }).join('');

    return `
      <div class="section">
        <h3>${t.scheduleTitle}</h3>
        ${scheduleList}
      </div>

      <div class="section schedule-form">
        <h3>${isEditing ? t.editSchedule : t.addSchedule}</h3>

        <div class="form-row">
          <label>${t.label}</label>
          <input type="text" class="input-label" value="${f.label}" placeholder="${this._lang === 'pl' ? 'np. Wieczorna prywatnosc' : 'e.g. Evening privacy'}" />
        </div>

        <div class="form-row">
          <label>${t.days[0]} - ${t.days[6]}</label>
          <div class="day-selector">${dayButtons}</div>
        </div>

        <div class="form-row time-row">
          <div class="time-group">
            <label>${t.from}</label>
            <input type="number" class="input-time input-start-hour" min="0" max="23" value="${f.startHour}" />
            <span>:</span>
            <input type="number" class="input-time input-start-min" min="0" max="59" step="5" value="${String(f.startMin).padStart(2, '0')}" />
          </div>
          <div class="time-group">
            <label>${t.to}</label>
            <input type="number" class="input-time input-end-hour" min="0" max="23" value="${f.endHour}" />
            <span>:</span>
            <input type="number" class="input-time input-end-min" min="0" max="59" step="5" value="${String(f.endMin).padStart(2, '0')}" />
          </div>
        </div>

        <div class="form-row">
          <label class="toggle-row">
            <input type="checkbox" class="input-repeat" ${f.repeat ? 'checked' : ''} />
            <span>${t.repeat}</span>
          </label>
        </div>

        <div class="form-buttons">
          <button class="btn btn-primary" data-action="save-schedule">${t.saveSchedule}</button>
          ${isEditing ? `<button class="btn btn-secondary" data-action="cancel-edit">${t.cancelEdit}</button>` : ''}
        </div>
      </div>
    `;
  }

  _buildHistoryTab() {
    const t = this._t;
    if (this._history.length === 0) {
      return `<div class="empty-state">${t.noHistory}</div>`;
    }

    const rows = [...this._history].reverse().slice(0, 30).map(h => {
      const date = new Date(h.ts);
      const dateStr = date.toLocaleDateString(this._lang === 'pl' ? 'pl-PL' : 'en-US', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
      });
      let typeLabel = '';
      let typeClass = '';
      switch (h.type) {
        case 'manual': typeLabel = t.manualPause; typeClass = 'type-manual'; break;
        case 'scheduled': typeLabel = t.scheduled; typeClass = 'type-scheduled'; break;
        case 'cancelled': typeLabel = t.cancelled; typeClass = 'type-cancelled'; break;
        default: typeLabel = t.completed; typeClass = 'type-completed';
      }
      return `<div class="history-row">
        <div class="history-date">${dateStr}</div>
        <div class="history-type ${typeClass}">${typeLabel}</div>
        <div class="history-duration">${h.minutes ? h.minutes + ' ' + t.min : '-'}</div>
        <div class="history-cameras">${h.cameras || 'all'}</div>
      </div>`;
    }).join('');

    return `
      <div class="section">
        <h3>${t.historyTitle}</h3>
        <div class="history-table">
          ${rows}
        </div>
      </div>
    `;
  }

  _buildSettingsTab() {
    const t = this._t;
    // Detect available notify services
    const notifyServices = this._hass ? Object.keys(this._hass.services.notify || {}).map(s => 'notify.' + s) : [];

    const serviceOptions = [
      `<option value="persistent_notification" ${this._notifyService === 'persistent_notification' ? 'selected' : ''}>${t.notifyPersistent}</option>`
    ];
    for (const svc of notifyServices) {
      const label = svc.replace('notify.', '').replace(/_/g, ' ');
      serviceOptions.push(`<option value="${svc}" ${this._notifyService === svc ? 'selected' : ''}>${label}</option>`);
    }

    return `
      <div class="section">
        <h3>\uD83D\uDD14 ${t.notifications}</h3>

        <div class="form-row">
          <label class="toggle-row">
            <input type="checkbox" class="input-notify-enabled" ${this._notifyEnabled ? 'checked' : ''} />
            <span>${t.notifyEnabled}</span>
          </label>
        </div>

        <div class="form-row">
          <label>${t.notifyService}</label>
          <select class="input-notify-service setting-select">
            ${serviceOptions.join('')}
          </select>
        </div>

        <div class="form-row">
          <label>${t.notifyBeforeEnd}</label>
          <div class="inline-input">
            <input type="number" class="input-time input-notify-before" min="1" max="30" value="${this._notifyBeforeEndMin}" />
            <span>${t.min}</span>
          </div>
        </div>

        <div class="notify-info">
          <p>\uD83D\uDD14 ${this._lang === 'pl'
            ? 'Powiadomienia beda wysylane: przy starcie prywatnosci, ' + this._notifyBeforeEndMin + ' min przed koncem (z informacja o kamerach), przy anulowaniu i przy wydluzeniu czasu.'
            : 'Notifications will be sent: on privacy start, ' + this._notifyBeforeEndMin + ' min before end (with camera info), on cancel, and on time extension.'
          }</p>
        </div>
      </div>

      <div class="section">
        <h3>\uD83D\uDCCB ${this._lang === 'pl' ? 'Integracja z Dashboard' : 'Dashboard Integration'}</h3>
        <p style="margin-bottom:12px;color:var(--bento-text-secondary);font-size:0.92em;">
          ${this._lang === 'pl'
            ? 'Mozesz dodac Frigate Privacy jako karte w swoim dashboard lub jako przycisk w Bubble Card.'
            : 'You can add Frigate Privacy as a card in your dashboard or as a Bubble Card button.'}
        </p>

        <div class="code-block">
          <div class="code-label">${this._lang === 'pl' ? 'Karta Lovelace (manual YAML)' : 'Lovelace Card (manual YAML)'}</div>
          <pre style="background:var(--bento-card);padding:10px;border-radius:6px;font-size:0.85em;overflow-x:auto;color:var(--bento-text);">type: custom:ha-frigate-privacy
# ${this._lang === 'pl' ? 'Opcjonalna konfiguracja:' : 'Optional config:'}
frigate_running_entity: binary_sensor.frigate_running
cameras:
  - camera.frigate_salon
  - camera.frigate_front
default_duration: 30</pre>
        </div>

        <div class="code-block" style="margin-top:12px;">
          <div class="code-label">Bubble Card - ${this._lang === 'pl' ? 'Przycisk nawigacji' : 'Navigation button'}</div>
          <pre style="background:var(--bento-card);padding:10px;border-radius:6px;font-size:0.85em;overflow-x:auto;color:var(--bento-text);">type: custom:bubble-card
card_type: button
name: Frigate Privacy
icon: mdi:camera-off
tap_action:
  action: navigate
  navigation_path: /ha-tools-panel
# ${this._lang === 'pl' ? 'Lub uzyj input_boolean do sterowania:' : 'Or use input_boolean for control:'}
# entity: input_boolean.frigate_privacy_mode</pre>
        </div>

        <div class="code-block" style="margin-top:12px;">
          <div class="code-label">\uD83D\uDDA5\uFE0F ${this._lang === 'pl' ? 'Dodawanie przez UI (edytor wizualny)' : 'Adding via UI (visual editor)'}</div>
          <div style="padding:10px 12px;background:var(--bento-bg);border-radius:6px;font-size:0.9em;line-height:1.8;color:var(--bento-text);">
            <ol style="margin:0;padding-left:18px;">
              <li>${this._lang === 'pl' ? 'Otw\u00F3rz dashboard \u2192 kliknij \u22EE \u2192 <strong>Edytuj</strong>' : 'Open your dashboard \u2192 click \u22EE \u2192 <strong>Edit dashboard</strong>'}</li>
              <li>${this._lang === 'pl' ? 'Kliknij <strong>+</strong> (dodaj kart\u0119)' : 'Click <strong>+</strong> (add card)'}</li>
              <li>${this._lang === 'pl' ? 'Wyszukaj <strong>Frigate Privacy</strong> na li\u015Bcie kart' : 'Search for <strong>Frigate Privacy</strong> in the card list'}</li>
              <li>${this._lang === 'pl' ? 'Wybierz kamer\u0119 z dropdown w edytorze' : 'Select cameras from the dropdown in the editor'}</li>
              <li>${this._lang === 'pl' ? 'Kliknij <strong>Zapisz</strong>' : 'Click <strong>Save</strong>'}</li>
            </ol>
            <p style="margin:8px 0 0 0;font-size:0.85em;color:var(--bento-text-secondary);">
              \uD83D\uDCA1 ${this._lang === 'pl' ? 'Je\u015Bli karta nie widoczna na li\u015Bcie \u2014 upewnij si\u0119 \u017Ce zas\u00F3b <code>ha-frigate-privacy.js</code> jest zaladowany (HACS lub r\u0119cznie).' : 'If the card is not listed \u2014 make sure the <code>ha-frigate-privacy.js</code> resource is loaded (HACS or manual).'}
            </p>
          </div>
        </div>

        <div class="code-block" style="margin-top:12px;">
          <div class="code-label">${this._lang === 'pl' ? 'Automatyzacja z input_boolean' : 'Automation with input_boolean'}</div>
          <pre style="background:var(--bento-card);padding:10px;border-radius:6px;font-size:0.85em;overflow-x:auto;color:var(--bento-text);">automation:
  - alias: "Frigate Privacy Toggle"
    trigger:
      - platform: state
        entity_id: input_boolean.frigate_privacy_mode
        to: "on"
    action:
      - service: mqtt.publish
        data:
          topic: frigate/clips/set
          payload: "OFF"
      - service: mqtt.publish
        data:
          topic: frigate/detect/set
          payload: "OFF"
      - delay: "01:00:00"
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.frigate_privacy_mode</pre>
        </div>
      </div>
    `;
  }

  _attachEvents() {
    const sr = this.shadowRoot;
    if (!sr) return;

    // Tabs
    sr.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this._activeTab = btn.dataset.tab;
        history.replaceState(null, '', location.pathname + '#' + this._toolId + '/' + this._activeTab);
        this._updateUI();
      });
    });

    // Camera selection
    sr.querySelectorAll('.camera-card').forEach(card => {
      card.addEventListener('click', () => {
        const camId = card.dataset.camera;
        if (camId === '__all__') {
          this._selectedCameras.clear();
        } else {
          if (this._selectedCameras.has(camId)) {
            this._selectedCameras.delete(camId);
          } else {
            this._selectedCameras.add(camId);
          }
        }
        this._updateUI();
      });
    });

    // Quick pause buttons
    sr.querySelectorAll('.btn-quick').forEach(btn => {
      btn.addEventListener('click', () => {
        this._pauseFrigate(parseInt(btn.dataset.minutes));
      });
    });

    // Custom pause
    const pauseCustom = sr.querySelector('[data-action="pause-custom"]');
    if (pauseCustom) {
      pauseCustom.addEventListener('click', () => {
        const input = sr.querySelector('.input-minutes');
        const mins = parseInt(input?.value) || 30;
        this._customMinutes = mins;
        this._pauseFrigate(mins);
      });
    }

    // Resume / Cancel
    sr.querySelectorAll('[data-action="resume"]').forEach(btn => {
      btn.addEventListener('click', () => this._resumeFrigate());
    });

    // Extend buttons
    sr.querySelectorAll('[data-extend]').forEach(btn => {
      btn.addEventListener('click', () => {
        this._extendPrivacy(parseInt(btn.dataset.extend));
      });
    });

    // Minutes input update
    const minutesInput = sr.querySelector('.input-minutes');
    if (minutesInput) {
      minutesInput.addEventListener('change', (e) => {
        this._customMinutes = parseInt(e.target.value) || 30;
      });
    }

    // Schedule form inputs
    const labelInput = sr.querySelector('.input-label');
    if (labelInput) {
      labelInput.addEventListener('input', (e) => { this._scheduleForm.label = e.target.value; });
    }

    sr.querySelectorAll('.day-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const day = parseInt(btn.dataset.day);
        const idx = this._scheduleForm.days.indexOf(day);
        if (idx >= 0) {
          this._scheduleForm.days.splice(idx, 1);
        } else {
          this._scheduleForm.days.push(day);
        }
        this._updateUI();
      });
    });

    const startHour = sr.querySelector('.input-start-hour');
    const startMin = sr.querySelector('.input-start-min');
    const endHour = sr.querySelector('.input-end-hour');
    const endMin = sr.querySelector('.input-end-min');
    if (startHour) startHour.addEventListener('change', (e) => { this._scheduleForm.startHour = parseInt(e.target.value); });
    if (startMin) startMin.addEventListener('change', (e) => { this._scheduleForm.startMin = parseInt(e.target.value); });
    if (endHour) endHour.addEventListener('change', (e) => { this._scheduleForm.endHour = parseInt(e.target.value); });
    if (endMin) endMin.addEventListener('change', (e) => { this._scheduleForm.endMin = parseInt(e.target.value); });

    const repeatInput = sr.querySelector('.input-repeat');
    if (repeatInput) {
      repeatInput.addEventListener('change', (e) => { this._scheduleForm.repeat = e.target.checked; });
    }

    // Save schedule
    const saveBtn = sr.querySelector('[data-action="save-schedule"]');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => this._saveScheduleFromForm());
    }

    const cancelBtn = sr.querySelector('[data-action="cancel-edit"]');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        this._resetScheduleForm();
        this._updateUI();
      });
    }

    // Schedule item actions
    sr.querySelectorAll('[data-schedule-toggle]').forEach(btn => {
      btn.addEventListener('click', () => this._toggleScheduleEnabled(parseInt(btn.dataset.scheduleToggle)));
    });
    sr.querySelectorAll('[data-schedule-edit]').forEach(btn => {
      btn.addEventListener('click', () => this._editSchedule(parseInt(btn.dataset.scheduleEdit)));
    });
    sr.querySelectorAll('[data-schedule-delete]').forEach(btn => {
      btn.addEventListener('click', () => this._deleteSchedule(parseInt(btn.dataset.scheduleDelete)));
    });

    // Settings: notification toggle
    const notifyEnabledCb = sr.querySelector('.input-notify-enabled');
    if (notifyEnabledCb) {
      notifyEnabledCb.addEventListener('change', (e) => {
        this._notifyEnabled = e.target.checked;
        this._saveNotifySettings();
      });
    }

    // Settings: notify service
    const notifyServiceSel = sr.querySelector('.input-notify-service');
    if (notifyServiceSel) {
      notifyServiceSel.addEventListener('change', (e) => {
        this._notifyService = e.target.value;
        this._saveNotifySettings();
      });
    }

    // Settings: notify before end
    const notifyBeforeInput = sr.querySelector('.input-notify-before');
    if (notifyBeforeInput) {
      notifyBeforeInput.addEventListener('change', (e) => {
        this._notifyBeforeEndMin = parseInt(e.target.value) || 5;
        this._saveNotifySettings();
      });
    }
  }

  _getCSS() {
    return `
* { box-sizing: border-box; margin: 0; padding: 0; }

.card {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  color: var(--bento-text);
  background: var(--bento-card) !important;
  border: 1px solid var(--bento-border) !important;
  border-radius: var(--bento-radius-md) !important;
  box-shadow: var(--bento-shadow-sm);
  overflow: hidden;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding: 16px 20px;
  background: var(--bento-card);
  border-radius: var(--bento-radius-sm);
  box-shadow: var(--bento-shadow-sm);
  border: 1px solid var(--bento-border);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon { font-size: 24px; }

.header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--bento-text);
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.status-running { background: rgba(16,185,129,0.12); color: var(--bento-success, #10B981); }
.status-running .status-dot { background: var(--bento-success, #10B981); }
.status-stopped { background: rgba(239,68,68,0.12); color: var(--bento-error, #EF4444); }
.status-stopped .status-dot { background: var(--bento-error, #EF4444); }
.status-unknown { background: rgba(148,163,184,0.12); color: var(--bento-text-secondary, #94a3b8); }
.status-unknown .status-dot { background: var(--bento-text-secondary, #94a3b8); }

/* Tabs */
.tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  background: var(--bento-card);
  padding: 4px;
  border-radius: var(--bento-radius-sm);
  border: 1px solid var(--bento-border);
  overflow-x: auto;
  flex-wrap: nowrap;
  -webkit-overflow-scrolling: touch;
}

.tab-btn {
  flex: 1;
  padding: 10px 16px;
  border: none;
  background: transparent;
  color: var(--bento-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border-radius: var(--bento-radius-xs);
  transition: var(--bento-transition);
}

.tab-btn:hover { background: rgba(59,130,246,0.06); color: var(--bento-text); }
.tab-btn.active { background: var(--bento-primary); color: #fff; }

/* Sections */
.section {
  background: var(--bento-card);
  border-radius: var(--bento-radius-sm);
  padding: 16px 20px;
  margin-bottom: 12px;
  box-shadow: var(--bento-shadow-sm);
  border: 1px solid var(--bento-border);
}

.section h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--bento-text);
}

/* Privacy active banner */
.privacy-active-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: linear-gradient(135deg, rgba(239,68,68,0.08), rgba(239,68,68,0.15));
  border: 1px solid rgba(239,68,68,0.25);
  border-radius: var(--bento-radius-sm);
  margin-bottom: 12px;
}

.privacy-icon { font-size: 32px; }

.privacy-info { flex: 1; }

.privacy-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--bento-error);
  margin-bottom: 2px;
}

.privacy-cameras-label {
  font-size: 12px;
  color: var(--bento-text-secondary);
  margin-bottom: 4px;
}

.privacy-banner-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-end;
}

.extend-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.extend-label {
  font-size: 11px;
  color: var(--bento-text-secondary);
  margin-right: 4px;
}

.btn-extend {
  padding: 5px 10px;
  border: 1px solid rgba(59,130,246,0.3);
  border-radius: var(--bento-radius-xs);
  background: rgba(59,130,246,0.08);
  color: var(--bento-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--bento-transition);
}

.btn-extend:hover {
  background: rgba(59,130,246,0.15);
  border-color: var(--bento-primary);
}

.countdown { display: flex; align-items: center; gap: 8px; }
.countdown-label { font-size: 12px; color: var(--bento-text-secondary); }
.countdown-value {
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--bento-error);
  letter-spacing: 1px;
}

/* Camera grid */
.camera-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}

.camera-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--bento-radius-sm);
  border: 2px solid var(--bento-border);
  cursor: pointer;
  transition: var(--bento-transition);
  background: var(--bento-bg);
}

.camera-card:hover {
  border-color: var(--bento-primary);
  background: rgba(59,130,246,0.04);
}

.camera-card.selected {
  border-color: var(--bento-primary);
  background: rgba(59,130,246,0.08);
}

.camera-status { font-size: 14px; }
.camera-name { font-size: 13px; flex: 1; font-weight: 500; }
.camera-check { font-size: 14px; color: var(--bento-primary); font-weight: 700; }

/* Quick buttons */
.quick-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: var(--bento-radius-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--bento-transition);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-quick {
  padding: 10px 20px;
  border: 2px solid var(--bento-border);
  border-radius: var(--bento-radius-sm);
  background: var(--bento-bg);
  color: var(--bento-text);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--bento-transition);
  min-width: 70px;
}

.btn-quick:hover {
  border-color: var(--bento-primary);
  background: rgba(59,130,246,0.06);
  color: var(--bento-primary);
}

.btn-primary { background: var(--bento-primary); color: #fff; }
.btn-primary:hover { background: var(--bento-primary-hover); }
.btn-success { background: var(--bento-success); color: #fff; }
.btn-success:hover { background: #059669; }
.btn-danger { background: var(--bento-error); color: #fff; }
.btn-danger:hover { background: #dc2626; }
.btn-secondary { background: var(--bento-bg); color: var(--bento-text); border: 1px solid var(--bento-border); }
.btn-secondary:hover { background: var(--bento-border); }
.btn-full { width: 100%; }

/* Custom pause */
.custom-pause {
  display: flex;
  align-items: center;
  gap: 8px;
}

.input-minutes {
  width: 80px;
  padding: 10px 12px;
  border: 1px solid var(--bento-border);
  border-radius: var(--bento-radius-xs);
  font-size: 14px;
  font-weight: 600;
  color: var(--bento-text);
  background: var(--bento-bg);
  text-align: center;
}

.input-suffix {
  font-size: 13px;
  color: var(--bento-text-secondary);
  margin-right: 8px;
}

/* Schedule items */
.schedule-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--bento-border);
}

.schedule-item:last-child { border-bottom: none; }

.schedule-item.disabled { opacity: 0.5; }

.schedule-main { flex: 1; }

.schedule-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--bento-text);
  margin-bottom: 2px;
}

.schedule-time {
  font-size: 13px;
  color: var(--bento-primary);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.schedule-days {
  font-size: 12px;
  color: var(--bento-text-secondary);
  margin-top: 2px;
}

.schedule-actions {
  display: flex;
  gap: 4px;
}

.btn-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: var(--bento-radius-xs);
  font-size: 16px;
  transition: var(--bento-transition);
}

.btn-icon:hover { background: rgba(59,130,246,0.08); }
.btn-icon-danger:hover { background: rgba(239,68,68,0.08); }

/* Schedule form */
.schedule-form { margin-top: 12px; }

.form-row {
  margin-bottom: 12px;
}

.form-row label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--bento-text-secondary);
  margin-bottom: 6px;
}

.input-label {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--bento-border);
  border-radius: var(--bento-radius-xs);
  font-size: 13px;
  color: var(--bento-text);
  background: var(--bento-bg);
}

.day-selector {
  display: flex;
  gap: 4px;
}

.day-btn {
  width: 40px;
  height: 36px;
  border: 2px solid var(--bento-border);
  border-radius: var(--bento-radius-xs);
  background: var(--bento-bg);
  color: var(--bento-text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--bento-transition);
}

.day-btn:hover { border-color: var(--bento-primary); }
.day-btn.active {
  background: var(--bento-primary);
  color: #fff;
  border-color: var(--bento-primary);
}

.time-row {
  display: flex;
  gap: 20px;
}

.time-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.time-group label {
  margin-bottom: 0;
  margin-right: 6px;
}

.time-group span {
  font-weight: 700;
  color: var(--bento-text-secondary);
}

.input-time {
  width: 52px;
  padding: 8px;
  border: 1px solid var(--bento-border);
  border-radius: var(--bento-radius-xs);
  font-size: 14px;
  font-weight: 600;
  color: var(--bento-text);
  background: var(--bento-bg);
  text-align: center;
}

.toggle-row {
  display: flex !important;
  align-items: center;
  gap: 8px;
  flex-direction: row !important;
  cursor: pointer;
}

.toggle-row input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: var(--bento-primary);
}

.toggle-row span {
  font-size: 13px;
  color: var(--bento-text);
}

.form-buttons {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

/* History */
.history-table {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.history-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--bento-border);
  font-size: 13px;
}

.history-row:last-child { border-bottom: none; }

.history-date { color: var(--bento-text-secondary); min-width: 120px; font-variant-numeric: tabular-nums; }
.history-type { font-weight: 600; min-width: 100px; }
.history-duration { min-width: 60px; color: var(--bento-text-secondary); }
.history-cameras { flex: 1; color: var(--bento-text-secondary); font-size: 12px; }

.type-manual { color: var(--bento-primary); }
.type-scheduled { color: var(--bento-success); }
.type-cancelled { color: var(--bento-warning); }
.type-completed { color: var(--bento-text-secondary); }

/* Settings */
.setting-select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--bento-border);
  border-radius: var(--bento-radius-xs);
  font-size: 13px;
  color: var(--bento-text);
  background: var(--bento-bg);
}

.inline-input {
  display: flex;
  align-items: center;
  gap: 8px;
}

.inline-input span {
  font-size: 13px;
  color: var(--bento-text-secondary);
}

.notify-info {
  margin-top: 16px;
  padding: 12px;
  background: rgba(59,130,246,0.05);
  border-radius: var(--bento-radius-xs);
  border: 1px solid rgba(59,130,246,0.1);
}

.notify-info p {
  font-size: 12px;
  color: var(--bento-text-secondary);
  line-height: 1.5;
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: 32px;
  color: var(--bento-text-secondary);
  font-size: 14px;
}

/* Toast */
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(100px);
  padding: 12px 24px;
  border-radius: var(--bento-radius-sm);
  font-size: 13px;
  font-weight: 500;
  z-index: 1000;
  opacity: 0;
  transition: all 0.3s ease;
  pointer-events: none;
}

.toast-show {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}

.toast-success { background: var(--bento-success); color: #fff; }
.toast-error { background: var(--bento-error); color: #fff; }
.toast-info { background: var(--bento-primary); color: #fff; }

/* Responsive */

        .tabs, .tab-bar { scrollbar-width: thin; scrollbar-color: var(--bento-border, #E2E8F0) transparent; }
        .tabs::-webkit-scrollbar, .tab-bar::-webkit-scrollbar { height: 4px; }
        .tabs::-webkit-scrollbar-track, .tab-bar::-webkit-scrollbar-track { background: transparent; }
        .tabs::-webkit-scrollbar-thumb, .tab-bar::-webkit-scrollbar-thumb { background: var(--bento-border, #E2E8F0); border-radius: 4px; }
@media (max-width: 768px) {
  .card { padding: 12px; }
  .camera-grid { grid-template-columns: 1fr 1fr; }
  .time-row { flex-direction: column; gap: 8px; }
  .header { flex-direction: column; gap: 10px; align-items: flex-start; }
  .privacy-active-banner { flex-direction: column; text-align: center; }
  .privacy-banner-actions { align-items: stretch; }
  .extend-row { justify-content: center; }
  .history-row { flex-wrap: wrap; }
  .day-btn { width: 36px; height: 32px; font-size: 11px; }
}

@media (max-width: 480px) {
  .camera-grid { grid-template-columns: 1fr; }
  .quick-buttons { flex-direction: column; }
  .btn-quick { width: 100%; }
  .custom-pause { flex-direction: column; align-items: stretch; }
  .custom-pause .input-minutes { width: 100%; }
}
`;
  }

  setActiveTab(tabId) {
    this._activeTab = tabId;
    this._updateUI();
  }
}

if (!customElements.get('ha-frigate-privacy')) {
  customElements.define('ha-frigate-privacy', HaFrigatePrivacy);
}
class HaFrigatePrivacyEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
  }
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }
  _dispatch() {
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: this._config }, bubbles: true, composed: true }));
  }
  _render() {
    if (!this._hass) return;
    this.shadowRoot.innerHTML = `
      <style>
            :host { display:block; padding:16px; }

@media (prefers-color-scheme: dark) {
  :host {
    --bento-bg: var(--primary-background-color, #1a1a2e);
    --bento-card: var(--card-background-color, #16213e);
    --bento-text: var(--primary-text-color, #e2e8f0);
    --bento-text-secondary: var(--secondary-text-color, #94a3b8);
    --bento-border: var(--divider-color, #334155);
    --bento-shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
    --bento-shadow-md: 0 4px 12px rgba(0,0,0,0.4);
  }
}
            h3 { margin:0 0 16px; font-size:15px; font-weight:600; color:var(--bento-text, var(--primary-text-color,#1e293b)); }
            input { outline:none; transition:border-color .2s; }
            input:focus { border-color:var(--bento-primary, var(--primary-color,#3b82f6)); }
        </style>
      <h3>Frigate Privacy</h3>
            <div style="margin-bottom:12px;">
              <label style="display:block;font-weight:500;margin-bottom:4px;font-size:13px;">Title</label>
              <input type="text" id="cf_title" value="${_esc(this._config?.title || 'Frigate Privacy')}"
                style="width:100%;padding:8px 12px;border:1px solid var(--divider-color,#e2e8f0);border-radius:8px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#1e293b);font-size:14px;box-sizing:border-box;">
            </div>
            <div style="margin-bottom:12px;">
              <label style="display:block;font-weight:500;margin-bottom:4px;font-size:13px;">Frigate addon ID</label>
              <input type="text" id="cf_frigate_addon_id" value="${_esc(this._config?.frigate_addon_id || 'ccab4aaf_frigate')}"
                style="width:100%;padding:8px 12px;border:1px solid var(--divider-color,#e2e8f0);border-radius:8px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#1e293b);font-size:14px;box-sizing:border-box;">
            </div>
    `;
        const f_title = this.shadowRoot.querySelector('#cf_title');
        if (f_title) f_title.addEventListener('input', (e) => {
          this._config = { ...this._config, title: e.target.value };
          this._dispatch();
        });
        const f_frigate_addon_id = this.shadowRoot.querySelector('#cf_frigate_addon_id');
        if (f_frigate_addon_id) f_frigate_addon_id.addEventListener('input', (e) => {
          this._config = { ...this._config, frigate_addon_id: e.target.value };
          this._dispatch();
        });
  }
  connectedCallback() { this._render(); }
}
if (!customElements.get('ha-frigate-privacy-editor')) { customElements.define('ha-frigate-privacy-editor', HaFrigatePrivacyEditor); }

})();

window.customCards = window.customCards || [];
window.customCards.push({ type: 'ha-frigate-privacy', name: 'Frigate Privacy', description: 'Pause Frigate cameras with timer and privacy schedule', preview: false });
