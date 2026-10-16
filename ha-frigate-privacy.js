/* Frigate Privacy v6.4.0 — integration-owned Home Assistant card */
(function () {
  'use strict';

// HA_FORMAT_UI_START
// Localized presentation; raw values remain available to callers for details/export.
function createFormatUi(language = 'en', timeZone = 'UTC', preferences = {}) {
  const hourCycle = preferences.hourCycle || 'h23';
  const dateLanguage = preferences.dateLanguage || language;
  const stamp = value => typeof value === 'number' ? (Number.isFinite(value) ? value : NaN) : typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value) ? Date.parse(value) : NaN;
  const localized = (value, options, locale = language) => {
    const time = stamp(value);
    if (!Number.isFinite(time)) return null;
    try { return new Intl.DateTimeFormat(locale, {timeZone, ...options}).format(time); } catch (_) { return null; }
  };
  const clock = (value, withOffset = false) => localized(value, {hour:'2-digit', minute:'2-digit', hourCycle, ...(withOffset ? {timeZoneName:'shortOffset'} : {})});
  const date = (value, short = false) => localized(value, {day:'numeric', month:'short', ...(short ? {} : {year:'numeric'})}, dateLanguage);
  const pointLabel = value => localized(value, {year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', hourCycle, timeZoneName:'shortOffset'});
  const chartLabels = (values, resolution = 'hour') => {
    const showDate = resolution === 'day' || values.length > 1 && stamp(values.at(-1)) - stamp(values[0]) >= 86400000;
    const labels = values.map(value => resolution === 'day' ? date(value, true) : `${showDate ? date(value, true) + ' ' : ''}${clock(value)}`);
    const counts = new Map();
    for (const label of labels) counts.set(label, (counts.get(label) || 0) + 1);
    return labels.map((label, index) => counts.get(label) < 2 ? label : resolution === 'day' ? pointLabel(values[index])
      : `${showDate ? date(values[index], true) + ' ' : ''}${clock(values[index], true)}`);
  };
  const key = JSON.stringify([language, timeZone, hourCycle, dateLanguage]);
  const numbers = new Intl.NumberFormat(language);
  const plurals = new Intl.PluralRules(language);
  const count = (value, forms) => `${numbers.format(value)} ${forms[plurals.select(value)] || forms.other}`;
  const dateTime = value => {
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(value)) return null;
    const time = Date.parse(value);
    if (!Number.isFinite(time)) return null;
    try { return new Intl.DateTimeFormat(dateLanguage, {timeZone, dateStyle:'medium', timeStyle:'short', hourCycle}).format(new Date(time)); }
    catch (_) { return null; }
  };
  const range = (from, to) => {
    const first = Date.parse(from), last = Date.parse(to);
    if (!Number.isFinite(first) || !Number.isFinite(last) || last < first) return null;
    try {
      const day = new Intl.DateTimeFormat(dateLanguage, {timeZone, dateStyle:'medium'});
      const clock = new Intl.DateTimeFormat(language, {timeZone, hour:'2-digit', minute:'2-digit', hourCycle});
      return day.format(first) === day.format(last)
        ? `${day.format(first)} (${clock.format(first)}–${clock.format(last)})`
        : `${dateTime(from)} – ${dateTime(to)}`;
    } catch (_) { return null; }
  };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const periodMarkup = ({start, end, label, source, measured, expected, unit, details = '', sourceTimeZone = ''}) => {
    const local = range(start, end);
    if (!local) return '';
    const coverage = typeof measured === 'number' && Number.isFinite(measured) && typeof expected === 'number' && Number.isFinite(expected)
      ? `${numbers.format(measured)}/${numbers.format(expected)} ${unit}` : '';
    const pl = String(language).startsWith('pl');
    return `<div class="energy-period-v4" style="overflow-wrap:anywhere"><p data-energy-period-summary>${[source, label, local, coverage, timeZone].filter(Boolean).map(escape).join(' · ')}</p><details data-energy-period-details data-energy-period-key="${escape(start + '|' + end)}"><summary style="min-height:44px;box-sizing:border-box;padding:12px 0;display:list-item;list-style-position:inside;cursor:pointer">${pl ? 'Źródło i szczegóły czasu' : 'Source and time details'}</summary><p>${escape(details)}</p>${sourceTimeZone && sourceTimeZone !== timeZone ? `<p>${escape(pl ? 'Strefa pomiarów i granic okresu' : 'Measurement calendar time zone')}: ${escape(sourceTimeZone)}</p>` : ''}<p>UTC: ${escape(start)} — ${escape(end)}</p></details></div>`;
  };
  const capturePeriods = (root, previous, current) => {
    if (!previous || ['epoch','connection','user'].some(key => previous[key] !== current[key])) return [];
    return [...root.querySelectorAll('[data-energy-period-key]')].map(element => ({
      key:element.dataset.energyPeriodKey, open:element.open, focused:root.activeElement === element.querySelector('summary')
    }));
  };
  const restorePeriods = (root, records) => {
    for (const element of root.querySelectorAll('[data-energy-period-key]')) {
      const record = records.find(row => row.key === element.dataset.energyPeriodKey);
      if (!record) continue;
      element.open = record.open;
      if (record.focused) element.querySelector('summary')?.focus({preventScroll:true});
    }
  };
  return {timeZone, key, clock, date, pointLabel, chartLabels, number:(value, options)=>options ? new Intl.NumberFormat(language, options).format(value) : numbers.format(value), count, dateTime, range, periodMarkup, capturePeriods, restorePeriods};
}
// Presentation follows the HA profile; measurement and tariff calendars remain separate.
createFormatUi.forHass = hass => {
  const locale = hass?.locale || {};
  const systemLanguage = typeof navigator !== 'undefined' ? navigator.language : undefined;
  const language = locale.language || hass?.language || systemLanguage || 'en';
  const validZone = value => {
    if (typeof value !== 'string' || !(value === 'UTC' || value.includes('/')) || /^[+-]/.test(value)) return null;
    try { new Intl.DateTimeFormat('en', {timeZone:value}).format(0); return value; } catch (_) { return null; }
  };
  let systemZone;
  try { systemZone = validZone(Intl.DateTimeFormat().resolvedOptions().timeZone); } catch (_) {}
  const serverZone = validZone(hass?.config?.time_zone);
  const timeZone = (locale.time_zone === 'server' ? serverZone : systemZone) || serverZone || 'UTC';
  const clockLanguage = locale.time_format === 'system' ? systemLanguage || language : language;
  const hourCycle = locale.time_format === '12' ? 'h12' : locale.time_format === '24' ? 'h23'
    : new Intl.DateTimeFormat(clockLanguage, {hour:'numeric'}).resolvedOptions().hourCycle;
  return createFormatUi(language, timeZone, {hourCycle, dateLanguage:locale.date_format === 'system' ? systemLanguage || language : language});
};
// HA_FORMAT_UI_END
// HA_LIST_UI_START
// Shared list presentation. No registry writes, storage or global state.
function createListUi(language = 'en') {
  const collator = new Intl.Collator(language, {numeric:true, sensitivity:'base'});
  const compare = (a,b) => collator.compare(String(a ?? ''), String(b ?? ''));
  const createdAt = value => {
    if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value * 1000 : 0;
    if (typeof value !== 'string' || !value.trim() || /^0(?:\.0+)?$/.test(value.trim())) return 0;
    const time = Date.parse(value);
    return Number.isFinite(time) && time > 0 ? time : 0;
  };
  const isNew = (value, now = Date.now()) => {
    const time = createdAt(value);
    return time > 0 && time <= now && now - time < 7 * 86400000;
  };
  return {compare, createdAt, isNew};
}
// HA_LIST_UI_END

// BEGIN canonical W4 closure SHA256 029c06206e55abad9aa09dfcf65bb13027ec24ce6a0bfacc45a938891b27254e
// HA Tools v3: vendored inside each consumer's own closure, never a window API.
function createUiV3({ language = 'en' } = {}) {
  const pl = String(language).startsWith('pl');
  const states = {
    success: ['Success', 'Sukces', '✓'],
    partial: ['Partial', 'Częściowo', '½'],
    unconfirmed: ['Unconfirmed', 'Niepotwierdzony', '?'],
    error: ['Error', 'Błąd', '✕'],
    not_checked: ['Not checked', 'Nie sprawdzono', '–'],
    no_data: ['No data', 'Brak danych', '∅'],
  };
  const status = (value) => {
    const code = typeof value === 'string' && Object.hasOwn(states, value) ? value : 'not_checked';
    const row = states[code];
    return { code, label: row[pl ? 1 : 0], icon: row[2], countsAsSuccess: code === 'success' };
  };
  const statusHtml = (value) => {
    const result = status(value);
    return `<span class="ht-result-state ht-result-state--${result.code}" data-result-state="${result.code}"><span aria-hidden="true">${result.icon}</span> ${result.label}</span>`;
  };
  const css = `
.ht-result-state { display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border:1px solid currentColor;border-radius:6px;font-size:12px;line-height:1.4;white-space:normal; }
.ht-result-state--success { color:#237b3d;background:rgba(35,123,61,.10); }
.ht-result-state--partial { color:#966400;background:rgba(150,100,0,.10); }
.ht-result-state--unconfirmed { color:#ad5200;background:rgba(173,82,0,.10); }
.ht-result-state--error { color:#c32b2b;background:rgba(195,43,43,.10); }
.ht-result-state--not_checked,.ht-result-state--no_data { color:var(--secondary-text-color,#666);background:transparent; }
.ht-result-state--no_data { border-style:dashed; }
:host(.bento-dark) .ht-result-state--success { color:#81cf99; }
:host(.bento-dark) .ht-result-state--partial { color:#efd080; }
:host(.bento-dark) .ht-result-state--unconfirmed { color:#ffb97b; }
:host(.bento-dark) .ht-result-state--error { color:#ff9999; }
`;
  return { status, statusHtml, css };
}
// END canonical W4 closure


  const sharedEsc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const _esc = (s) => sharedEsc(String(s == null ? '' : s));
  const haToolsPersistence = {
    loadSync(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    save(key, value) { try { localStorage.setItem(key, String(value)); } catch (_) { /* optional UI preference */ } },
  };

  const CSS = `
    :host {
      --fp-primary: var(--primary-color, #6366f1); --fp-primary-2: #8b5cf6;
      --fp-card: var(--card-background-color, #ffffff); --fp-bg: var(--primary-background-color, #f6f7fb);
      --fp-soft: color-mix(in srgb, var(--fp-primary) 9%, var(--fp-card));
      --fp-border: var(--divider-color, #e4e7ec); --fp-text: var(--primary-text-color, #101828);
      --fp-muted: var(--secondary-text-color, #667085); --fp-success: #18763b; --fp-warning: #795100; --fp-danger: #b42318; --fp-on-danger: #fff;
      display: block; color: var(--fp-text); font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 15px; line-height: 1.55; -webkit-font-smoothing: antialiased;
    }
    :host(.bento-dark) {
      --fp-card: var(--card-background-color, #151821); --fp-bg: var(--primary-background-color, #0e1117);
      --fp-border: var(--divider-color, #2b3140); --fp-text: var(--primary-text-color, #f4f6fb);
      --fp-success:#81cf99; --fp-warning:#efd080; --fp-danger:#ff9999; --fp-on-danger:#101828;
      --fp-muted: var(--secondary-text-color, #aab2c0); --fp-soft: color-mix(in srgb, var(--fp-primary) 15%, var(--fp-card)); color-scheme: dark;
    }
    :host .ht-result-state { background:transparent; }
    :host(:not(.bento-dark)) .ht-result-state--partial { color:#795100; }
    * { box-sizing: border-box; } button, input, select, textarea { font: inherit; } .channel-badge{display:inline-flex;align-items:center;gap:5px;padding:4px 7px;border:1px solid var(--fp-border);border-radius:8px;background:var(--fp-soft)} .channel-badge ha-icon{--mdc-icon-size:17px} .channel-hint{margin-top:12px} .action-example{width:100%;min-height:240px;resize:vertical;padding:12px;background:var(--fp-bg);color:var(--fp-text);border:1px solid var(--fp-border);border-radius:12px;font:13px/1.6 ui-monospace,monospace;white-space:pre} .action-kind{max-width:100%;min-height:44px;margin-bottom:12px;background:var(--fp-card);color:var(--fp-text);border:1px solid var(--fp-border);border-radius:10px;padding:8px} .action-links{display:flex;flex-wrap:wrap;gap:12px;margin-top:14px}
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible { outline: 3px solid color-mix(in srgb, var(--fp-primary) 35%, transparent); outline-offset: 2px; }
    .card { overflow: hidden; background: var(--fp-card); border: 1px solid var(--fp-border); border-radius: 24px; box-shadow: 0 18px 50px rgba(16, 24, 40, .10); }
    .header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 24px 24px 18px; border-bottom: 1px solid var(--fp-border); background: linear-gradient(135deg, var(--fp-soft), transparent 62%); }
    .brand { display: flex; align-items: center; gap: 13px; min-width: 0; }
    .brand-mark { width: 44px; height: 44px; border-radius: 14px; display: grid; place-items: center; color: white; background: linear-gradient(135deg, var(--fp-primary), var(--fp-primary-2)); box-shadow: 0 8px 24px color-mix(in srgb, var(--fp-primary) 30%, transparent); }
    .brand-mark ha-icon { --mdc-icon-size: 24px; } h2, h3, p { margin: 0; } h2 { font-size: 22px; line-height: 1.25; letter-spacing: -.025em; }
    .subtitle { margin-top: 5px; color: var(--fp-muted); font-size: 14px; line-height: 1.45; }
    .status-pill { display: inline-flex; align-items: center; gap: 8px; min-height: 36px; padding: 7px 12px; border-radius: 999px; border: 1px solid var(--fp-border); background: var(--fp-card); color: var(--fp-muted); font-size: 13px; line-height: 1.35; font-weight: 750; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #98a2b3; }
    .status-pill.paused .status-dot { background: var(--fp-success); box-shadow: 0 0 0 4px color-mix(in srgb, var(--fp-success) 16%, transparent); }
    .status-pill.resuming .status-dot, .status-pill.recovering .status-dot { background: var(--fp-warning); } .status-pill.partial .status-dot, .status-pill.error .status-dot { background: var(--fp-danger); }
    .body { padding: 20px 24px 24px; }
    .intro-banner, .notice, .donate-section { border: 1px solid var(--fp-border); border-radius: 18px; background: var(--fp-soft); }
    .intro-banner { position: relative; padding: 18px 50px 18px 18px; margin-bottom: 18px; }
    .intro-headline { padding-right:48px; display: flex; align-items: center; gap: 10px; font-size: 16px; line-height: 1.4; font-weight: 800; } .intro-headline ha-icon { color: var(--fp-primary); }
    .intro-steps { margin: 13px 0 0; padding-left: 24px; color: var(--fp-muted); font-size: 14px; line-height: 1.65; }
    .intro-dismiss { position: absolute; top: 12px; right: 12px; width: 44px; height: 44px; display: grid; place-items: center; border: 1px solid var(--fp-border); border-radius: 999px; background: var(--fp-card); color: var(--fp-muted); cursor: pointer; }
    .intro-dismiss ha-icon { --mdc-icon-size: 17px; }
    .notice { display: flex; gap: 14px; padding: 18px; } .notice > ha-icon { flex: 0 0 auto; color: var(--fp-primary); } .notice.error > ha-icon { color: var(--fp-danger); }
    .notice h3 { margin-bottom: 6px; font-size: 16px; line-height: 1.35; } .notice p { color: var(--fp-muted); font-size: 14px; line-height: 1.6; }
    .tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 4px; padding: 4px; margin-bottom: 18px; border-radius: 14px; background: var(--fp-bg); }
    .tab-btn { min-height: 44px; padding: 9px 10px; border: 0; border-radius: 11px; background: transparent; color: var(--fp-muted); cursor: pointer; font-size: 13.5px; line-height: 1.35; font-weight: 750; }
    .tab-btn.active { background: var(--fp-card); color: var(--fp-primary); box-shadow: 0 2px 9px rgba(16,24,40,.08); }
    .section { margin-top: 18px; padding: 20px; border: 1px solid var(--fp-border); border-radius: 18px; } .section:first-child { margin-top: 0; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 16px; } .section h3 { font-size: 16px; line-height: 1.4; letter-spacing: -.01em; }
    .helper { color: var(--fp-muted); font-size: 13.5px; line-height: 1.6; }
    .camera-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; }
    .camera-card { display: flex; align-items: center; gap: 11px; min-height: 58px; padding: 14px; border: 1px solid var(--fp-border); border-radius: 14px; background: var(--fp-card); cursor: pointer; transition: border-color .18s, background .18s, transform .18s; }
    .camera-grid > .camera-card { grid-column: 1 / -1; }
    .camera-card:hover { transform: translateY(-1px); border-color: color-mix(in srgb, var(--fp-primary) 45%, var(--fp-border)); } .camera-card.selected { border-color: var(--fp-primary); background: var(--fp-soft); }
    .camera-card ha-icon { flex: 0 0 auto; color: var(--fp-primary); --mdc-icon-size: 22px; } .camera-name { min-width: 0; overflow-wrap: break-word; font-size: 14px; line-height: 1.4; font-weight: 700; } .camera-check { margin-left: auto; color: var(--fp-primary); }
    .camera-tile { min-width: 0; padding: 8px; border: 1px solid var(--fp-border); border-radius: 14px; } .camera-tile .camera-card { border: 0; padding: 7px; min-height: 42px; }
    .channel-status { display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0; } .channel-status span { padding: 3px 7px; border-radius: 7px; background: var(--fp-bg); color: var(--fp-muted); font-size: 12px; }
    .preview-btn { min-height: 34px; padding: 5px 8px; border: 1px solid var(--fp-border); border-radius: 8px; background: var(--fp-card); color: var(--fp-primary); cursor: pointer; font-size: 12px; font-weight: 700; }
    .channel-status .channel-badge[data-channel-state="on"] { color:var(--fp-success);border-color:currentColor; }
    .channel-status .channel-badge[data-channel-state="off"],.channel-status .channel-badge[data-channel-state="idle"] { color:var(--fp-muted); }
    .channel-status .channel-badge[data-channel-state="unknown"],.channel-status .channel-badge[data-channel-state="mixed"] { color:var(--fp-warning);border-color:currentColor; }
    .channel-status .channel-badge[data-channel-state="unavailable"] { color:var(--fp-danger);border-color:currentColor; }
    .camera-feedback { display:grid;gap:8px;padding:12px 0;margin:8px 0;border-top:1px solid var(--fp-border);overflow-wrap:anywhere; }
    [data-video-stop-unconfirmed] { color:var(--fp-warning); }
    .camera-feedback .phase { justify-self:start; } .phase.pausing { color:var(--fp-warning); }
    .camera-deadline-row {display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}.camera-progress{width:100%;height:5px;accent-color:var(--fp-primary);display:block;margin:7px 0}.notification-steps{padding-inline-start:24px;line-height:1.6}.notification-steps li+li{margin-top:8px}.notification-actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.notification-actions .btn{min-height:44px;text-align:center;text-decoration:none}.status-pill[data-camera-summary]{cursor:pointer;font:inherit;min-height:44px}.status-pill[data-camera-summary]:focus-visible{outline:2px solid var(--fp-primary);outline-offset:3px}
    .camera-countdown { font-weight:750;font-variant-numeric:tabular-nums;overflow-wrap:anywhere; }
    .camera-preview { margin-top:12px;display:grid;gap:8px;min-width:0; } [data-preview-host] { min-width:0;overflow:hidden;border-radius:12px; }
    .seg { display: flex; gap: 5px; padding: 4px; border-radius: 13px; background: var(--fp-bg); }
    .seg-item { flex: 1; min-height: 42px; padding: 8px 10px; border: 0; border-radius: 10px; background: transparent; color: var(--fp-muted); cursor: pointer; font-size: 13.5px; line-height: 1.35; font-weight: 700; }
    .seg-item.selected { background: var(--fp-card); color: var(--fp-primary); box-shadow: 0 2px 8px rgba(16,24,40,.08); }
    .duration-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; margin-top: 12px; }
    input, select { min-height: 42px; width: 100%; padding: 9px 11px; border: 1px solid var(--fp-border); border-radius: 11px; background: var(--fp-card); color: var(--fp-text); }
    .btn { min-height: 44px; padding: 10px 16px; border: 1px solid transparent; border-radius: 12px; cursor: pointer; font-size: 14px; line-height: 1.35; font-weight: 800; } .btn:disabled { cursor: not-allowed; opacity: .55; }
    .btn-primary { color: white; background: linear-gradient(135deg, #4f46e5, #7c3aed); } .btn-secondary { color: var(--fp-text); background: var(--fp-card); border-color: var(--fp-border); } .btn-danger { color: var(--fp-on-danger); background: var(--fp-danger); } .btn-full { width: 100%; margin-top: 14px; }
    .state-grid { display: grid; gap: 12px; } .state-row { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 14px 16px; padding: 16px; border: 1px solid var(--fp-border); border-radius: 14px; }
    .state-name { font-size: 15px; line-height: 1.4; font-weight: 750; } .state-meta { margin-top: 7px; color: var(--fp-muted); font-size: 13px; line-height: 1.6; overflow-wrap: break-word; }
    .evidence { grid-column: 1 / -1; color: var(--fp-muted); font-size: 12.5px; line-height: 1.55; } .evidence summary { cursor: pointer; font-weight: 750; } .evidence-list { display: grid; gap: 6px; margin-top: 9px; overflow-wrap: anywhere; }
    .state-actions { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 9px; }
    .phase { align-self: start; padding: 6px 10px; border-radius: 999px; background: var(--fp-bg); font-size: 12.5px; line-height: 1.35; font-weight: 800; } .phase.paused { color: var(--fp-success); } .phase.resuming { color: var(--fp-warning); } .phase.partial, .phase.error { color: var(--fp-danger); }
    .schedule-list { display: grid; gap: 11px; } .schedule-item { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 14px; padding: 15px; border: 1px solid var(--fp-border); border-radius: 14px; }
    .schedule-title { font-size: 14px; line-height: 1.4; font-weight: 750; } .schedule-meta { margin-top: 6px; color: var(--fp-muted); font-size: 13px; line-height: 1.5; overflow-wrap: break-word; } .schedule-actions { display: flex; gap: 7px; }
    .icon-btn { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid var(--fp-border); border-radius: 10px; background: var(--fp-card); color: var(--fp-muted); cursor: pointer; } .icon-btn ha-icon { --mdc-icon-size: 18px; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 13px; } .field label { display: block; margin-bottom: 7px; color: var(--fp-muted); font-size: 13px; line-height: 1.4; font-weight: 700; } .field-wide { grid-column: 1 / -1; }
    .days { display: grid; grid-template-columns: repeat(7, minmax(0,1fr)); gap: 5px; } .day-btn { min-height: 40px; padding: 7px 4px; border: 1px solid var(--fp-border); border-radius: 9px; background: var(--fp-card); color: var(--fp-muted); cursor: pointer; font-size: 12.5px; line-height: 1.3; font-weight: 800; } .day-btn.selected { border-color: var(--fp-primary); background: var(--fp-soft); color: var(--fp-primary); }
    .form-actions { display: flex; gap: 9px; margin-top: 13px; }
    .donate-section { display: flex; align-items: center; justify-content: flex-start; gap: 8px; margin-top: 8px; padding: 4px 0; font-size: 11px; background:none; border:0; box-shadow:none; } .donate-section button { margin-left:auto; padding:2px 6px; min-height:0; line-height:1; border:0; background:transparent; color:var(--fp-muted); cursor:pointer; } .donate-section .donate-btn { min-height:0; padding:0; border:0; border-radius:0; background:none; color:var(--fp-muted); text-decoration:underline; font-size:11px; line-height:1.35; font-weight:400; } .donate-text h3 { font-size: 15px; line-height: 1.4; } .donate-text p { margin-top: 6px; color: var(--fp-muted); font-size: 13.5px; line-height: 1.55; }
    .donate-buttons { display: flex; gap: 9px; } .donate-btn { display: inline-flex; align-items: center; gap: 7px; min-height: 42px; padding: 9px 12px; border: 1px solid var(--fp-border); border-radius: 11px; background: var(--fp-card); color: var(--fp-text); text-decoration: none; font-size: 13px; line-height: 1.35; font-weight: 750; } .donate-btn ha-icon { --mdc-icon-size: 18px; color: var(--fp-primary); }
    .toast { position: fixed; left: 50%; bottom: 24px; z-index: 10; max-width: min(90vw, 520px); transform: translate(-50%, 90px); opacity: 0; pointer-events: none; padding: 12px 17px; border-radius: 11px; background: #101828; color: #fff; transition: .22s; font-size: 14px; line-height: 1.45; } .toast.show { transform: translate(-50%, 0); opacity: 1; } .toast.error { color:var(--fp-on-danger); background: var(--fp-danger); }
    .empty { padding: 24px; text-align: center; color: var(--fp-muted); font-size: 14px; line-height: 1.55; }

    .donate-section button, .donate-section .donate-btn { min-width:44px;min-height:44px; }
    .history-panel { min-width:0;container-type:inline-size; } .period-toolbar { display:flex;flex-wrap:wrap;gap:10px;align-items:end;margin:16px 0; }
    .period-toolbar label { color:var(--fp-muted);font-size:13px; } .period-toolbar select { display:block;min-height:44px;min-width:100px;margin-top:5px; }
    .period-timeline { list-style:none;padding:0;margin:18px 0;display:grid;gap:10px; }
    .period-timeline li { display:grid;grid-template-columns:minmax(90px,.6fr) minmax(0,1.6fr) auto;gap:12px;align-items:start;border:1px solid var(--fp-border);border-left:3px solid var(--fp-primary);padding:14px;border-radius:12px;background:var(--fp-bg); }
    .period-select { min-height:44px;min-width:44px;max-width:100%;padding:9px 12px;border:1px solid var(--fp-border);border-radius:10px;background:var(--fp-card);color:var(--fp-text);overflow-wrap:anywhere;text-align:start;cursor:pointer; }
    .period-select.selected { border-color:var(--fp-primary);background:var(--fp-soft);box-shadow:inset 0 0 0 1px var(--fp-primary); }
    .period-event { display:grid;gap:2px;font-size:14px;overflow-wrap:anywhere; } .period-event > span:nth-child(odd) { color:var(--fp-muted);font-size:12px; }
    .period-pagination { display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin:16px 0;font-size:13px; }
    .period-detail { padding:18px;margin-top:16px;border:1px solid var(--fp-border);border-radius:14px;overflow-wrap:anywhere; }
    .period-detail h3 { margin-bottom:12px; } .period-detail p { margin:10px 0; }
    .period-detail dl { display:grid;grid-template-columns:minmax(120px,.8fr) minmax(0,1.2fr);gap:6px 12px;margin:12px 0; }
    .period-detail dt { color:var(--fp-muted);font-size:13px; } .period-detail dd { margin:0;font-size:14px; }
    .period-evidence { margin-top:18px; } .period-evidence h4 { margin:0 0 10px; } .period-evidence > div { border-top:1px solid var(--fp-border);padding:12px 0; } .period-evidence code { display:block;font-size:12px;overflow-wrap:anywhere; }
    .period-table-wrap { max-width:100%;overflow:auto;overscroll-behavior:contain; } .period-table { width:100%;border-collapse:collapse;font-size:13px; } .period-table caption { text-align:start;color:var(--fp-muted);padding:10px 0; }
    .period-table th,.period-table td { text-align:start;vertical-align:top;border-bottom:1px solid var(--fp-border);padding:10px;overflow-wrap:anywhere; } .period-table th { font-weight:700;color:var(--fp-muted); }
    .history-panel button,.history-panel select { min-height:44px; } .history-panel button:focus-visible,.history-panel select:focus-visible { outline:3px solid var(--fp-primary);outline-offset:3px; }
    @media (max-width:620px) { .period-timeline li { grid-template-columns:1fr; } .period-detail dl { grid-template-columns:1fr;gap:3px; } .period-detail dd { margin-bottom:9px; } .period-toolbar > button { flex:1; } .period-table th,.period-table td { min-width:110px; } }

    @container (max-width:499px) {
      .period-table,.period-table tbody { display:block; }
      .period-table thead { position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%); }
      .period-table tr { display:grid;gap:8px;border:1px solid var(--fp-border);border-radius:12px;margin:12px 0;padding:12px; }
      .period-table td { display:block;min-width:0;border:0;padding:0; }
      .period-table td::before { content:attr(data-label);display:block;color:var(--fp-muted);font-size:12px;margin-bottom:4px; }
      .period-table-wrap { overflow:visible; }
    }

    :host{container-type:inline-size}
    button,input,select,textarea,a,[role="button"],summary{min-height:44px;min-width:44px;max-width:100%;box-sizing:border-box}
    button,select,summary,a{white-space:normal;overflow-wrap:anywhere}
    .icon-btn{width:44px;height:44px}.camera-tile .camera-card,.preview-btn,.seg-item,.day-btn{min-height:44px}
    .tabs{display:flex;flex-wrap:wrap}.tab-btn{flex:1 1 auto}.seg,.schedule-actions,.form-actions,.days{display:flex;flex-wrap:wrap}.seg-item{flex:1 1 90px}.day-btn{flex:0 0 44px}
    .tab-picker{margin-bottom:18px}.brand>div:last-child{min-width:0}.brand-mark{flex:0 0 44px}.brand h2{overflow-wrap:anywhere}
    .action-links a,summary{display:flex;align-items:center}button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible,[role="button"]:focus-visible,summary:focus-visible{outline:3px solid var(--fp-primary);outline-offset:2px}
    [hidden]{display:none!important}
    @container(max-width:620px){.header,.body{padding-left:16px;padding-right:16px}.header{align-items:flex-start;flex-wrap:wrap}.brand{width:100%}.status-pill{max-width:100%;margin-left:0}.camera-grid,.form-grid,.state-row,.schedule-item,.duration-row{grid-template-columns:minmax(0,1fr)}.field-wide{grid-column:auto}.section{padding:14px}.period-timeline li{grid-template-columns:minmax(0,1fr)}.period-detail dl{grid-template-columns:minmax(0,1fr)}.phase{justify-self:start}.donate-section{flex-wrap:wrap}}
    @media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; transition: none !important; } }
    @media (max-width: 620px) { .header, .body { padding-left: 16px; padding-right: 16px; } .header { align-items: flex-start; flex-wrap: wrap; } .brand { width: 100%; } .status-pill { max-width: 100%; margin-left: 57px; } .tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; } .camera-grid, .form-grid, .state-row, .schedule-item { grid-template-columns: 1fr; } .phase { justify-self: start; } .field-wide { grid-column: auto; } .days { grid-template-columns: repeat(4, minmax(0, 1fr)); } .donate-section { flex-direction: row; align-items: center; } .donate-buttons { flex-direction: column; } .duration-row { grid-template-columns: 1fr; } }
  `;

  class HaFrigatePrivacy extends HTMLElement {
    constructor() {
      super(); this.attachShadow({ mode: 'open' }); this._config = {}; this._hass = null;
      this._lang = (navigator.language || '').startsWith('pl') ? 'pl' : 'en'; this._activeTab = 'control';
      this._integrationChecked = false; this._integrationAvailable = false; this._recoveryReady = true; this._permissionDenied = false; this._declaredAdmin = false; this._busy = false; this._mutationWire = null; this._mutationOutcome = null; this._error = '';
      this._requestEpoch = 0; this._connectPromise = null; this._lastStatePollAt = 0; this._connection = null; this._userId = null; this._instanceId = null; this._declaredActive = true; this._cameras = []; this._schedules = []; this._paused = {}; this._lastOperations = {}; this._selectedCameras = new Set();
      this._customMinutes = Number(haToolsPersistence.loadSync('ha-frigate-privacy-pause-minutes')) || 30;
      const storedScope = haToolsPersistence.loadSync('ha-frigate-privacy-pause-stream-type'); this._pauseStreamType = ['all','main','sub'].includes(storedScope) ? storedScope : 'all';
      this._periodEpoch = 0; this._periods = []; this._periodInfo = null; this._periodState = 'idle';
      this._periodDays = 30; this._periodPage = 0; this._periodView = 'timeline'; this._periodSelected = null;
      this._periodWire = null; this._periodDeadline = null; this._periodContextKey = null; this._periodProducerKey = null;
      this._periodCallWS = null; this._periodContextConnection = null; this._periodBoundConnection = null;
      this._periodConnectionOffline = false; this._historyBrowserOnline = navigator.onLine !== false;
      this._periodDisconnected = () => { this._periodConnectionOffline = true; this._clearPrivateState(); this._invalidatePeriods('offline'); this._updateUI(); };
      this._periodReady = () => { this._periodConnectionOffline = false; this._invalidatePeriods('discarded'); this._updateUI(); };
      this._periodOffline = () => { this._historyBrowserOnline = false; this._clearPrivateState(); this._invalidatePeriods('offline'); this._updateUI(); };
      this._periodOnline = () => { this._historyBrowserOnline = true; this._invalidatePeriods('discarded'); this._updateUI(); };
      this._editingScheduleIdx = null; this._scheduleForm = this._emptySchedule(); this._lastHtml = ''; this._toastTimer = null;
      this._previewCamera = null; this._previewNode = null; this._previewLoad = null; this._previewEpoch = 0; this._previewFailed = false;
      this._cameraActions = Object.create(null);
      this._notifications=null;this._notificationWire=null;this._notificationResult=null;this._notificationEpoch=0;this._notificationTimer=null;
    }

    connectedCallback() {
      this._bindPeriodConnection();
      window.addEventListener('offline', this._periodOffline);
      window.addEventListener('online', this._periodOnline);
      this._invalidatePeriods('idle'); this._updateUI();
      if (!this._countdownTimer) this._countdownTimer = setInterval(() => this._tickCountdowns(), 1000);
      if (this._statePollTimer) return;
      this._statePollTimer = setInterval(() => {
        if (this.isConnected && this._hass?.user?.is_admin === true && this._hass.user.is_active !== false && this._historyBrowserOnline && !this._periodConnectionOffline && !this._permissionDenied && !this._connectPromise && !this._busy && Date.now() - this._lastStatePollAt >= 15000) this._connectIntegration();
      }, 15000);
    }

    static getConfigElement() { return document.createElement('ha-frigate-privacy-editor'); }
    static getStubConfig() { return { type: 'custom:ha-frigate-privacy', title: 'Frigate Privacy' }; }
    getCardSize() { return 7; } getGridOptions() { return { columns: 12, min_rows: 4, min_columns: 6 }; }
    _repairMojibake(str) { if (!str) return str; try { return decodeURIComponent(escape(str)); } catch (_) { return str; } }

    get _t() {
      const strings = {
        pl: { subtitle:'Prywatność kamer sterowana przez integrację',online:'Integracja gotowa',connecting:'Łączenie',recovering:'Bezpieczne odzyskiwanie stanu',recoveringHint:'Integracja czeka na encje Frigate i zachowuje zapisane cele. Sterowanie pozostaje zablokowane do zakończenia uzgadniania.',adminRequired:'Wymagane uprawnienia administratora',adminHint:'Stan kamer i harmonogramy mogą ujawniać rytm domu. Ta karta jest dostępna wyłącznie dla administratorów Home Assistant.',unavailable:'Integracja Frigate Privacy jest niedostępna',unavailableHint:'Dodaj lub napraw integrację, a następnie odśwież kartę. Żadne sterowanie awaryjne w przeglądarce nie zostanie uruchomione.',retry:'Spróbuj ponownie',retryResume:'Ponów bezpieczne wznowienie',introTitle:'Bezpieczny tryb prywatności',intro1:'Wybierz kamery, zakres i czas.',intro2:'Integracja zapisze stan przed zmianą.',intro3:'Częściowe lub niepewne wykonanie pozostanie widoczne.',control:'Sterowanie',schedule:'Harmonogram',state:'Stan',info:'Informacje',cameras:'Kamery',all:'Wszystkie kamery',scope:'Zakres',allScope:'Wszystko',main:'Nagrywanie',sub:'Detekcja',duration:'Czas w minutach',pause:'Włącz prywatność',resume:'Wznów bezpiecznie',noCameras:'Nie znaleziono kamer Frigate.',schedules:'Okna prywatności',noSchedules:'Brak harmonogramów.',add:'Dodaj harmonogram',edit:'Edytuj',save:'Zapisz',cancel:'Anuluj',remove:'Usuń',label:'Etykieta',start:'Początek',end:'Koniec',enabled:'Aktywny',days:['Pn','Wt','Śr','Cz','Pt','So','Nd'],currentState:'Stan potwierdzony przez backend',noActive:'Brak aktywnych przejść prywatności.',lastVerified:'Ostatnia zweryfikowana operacja',noHistory:'Brak zakończonych operacji.',source:'Źródło',deadline:'Termin',reason:'Powód',operation:'Operacja',observed:'Zweryfikowano',attempts:'Próby wznowienia',evidence:'Dowody per cel',architecture:'Model bezpieczeństwa',architectureText:'Karta nie steruje kamerami, przełącznikami ani konfiguracją HA bezpośrednio. Wszystkie odczyty i zmiany przechodzą przez administracyjne komendy WebSocket integracji. Harmonogram i odzyskiwanie po restarcie są własnością backendu.',support:'Podoba Ci się Frigate Privacy?',supportText:'Możesz wesprzeć dalszy rozwój i testy.',saved:'Zapisano',failed:'Operacja nie powiodła się',close:'Zamknij',snapshots:'Zdjęcia',detection:'Detekcja',soundHint:'Stan detekcji dźwięku nie potwierdza przechwytywania mikrofonu ani odsłuchu.',actions:'Przyciski i automatyzacje',actionHint:'Wybierz kamery, zakres i czas w Sterowaniu, a następnie użyj gotowej akcji w Home Assistant.',trustHint:'Jeśli prywatność ma włączać automatyzacja lub fizyczny przycisk: najpierw utwórz automatyzację w HA z poniższą akcją i własnym wyzwalaczem. Następnie otwórz Ustawienia → Urządzenia i usługi → Frigate Privacy → Konfiguruj. W polu Zaufane automatyzacje i skrypty wybierz tylko tę automatyzację i zapisz. Bez tego automatyzacja nie może sterować prywatnością.',example:'Przykład przypisania',copy:'Kopiuj',copied:'Skopiowano',notificationSettings:'Powiadomienia i zaufane akcje',buttonPause:'Przycisk pauzy',buttonResume:'Przycisk wznowienia',scriptPause:'Skrypt pauzy',scriptResume:'Skrypt wznowienia',automationPause:'Akcja automatyzacji / fizycznego przycisku',sceneHelper:'Scena z pomocnikiem',sceneHint:'Sceny HA zapisują stany. Dodaj pomocnik Przełącznik, ustaw go w scenie, a poniższą automatyzację dodaj do zaufanych akcji. Wybierz własny wyzwalacz fizycznego przycisku w edytorze HA.',video:'Obraz',recording:'Nagrywanie',soundDetection:'Detekcja dźwięku',preview:'Podgląd w HA',statusOn:'Wł.',statusOff:'Wył.',statusIdle:'Gotowa',statusUnavailable:'Niedostępna',statusUnknown:'Nieznany' },
        en: { subtitle:'Integration-owned camera privacy',online:'Integration ready',connecting:'Connecting',recovering:'Safely recovering state',recoveringHint:'The integration is waiting for Frigate entities while preserving exact saved targets. Controls remain locked until reconciliation finishes.',adminRequired:'Administrator permission required',adminHint:'Camera topology and schedules can reveal household routines. This card is available only to Home Assistant administrators.',unavailable:'Frigate Privacy integration is unavailable',unavailableHint:'Add or repair the integration, then refresh the card. No browser-side emergency control will run.',retry:'Retry',retryResume:'Retry safe resume',introTitle:'Safe privacy control',intro1:'Choose cameras, scope, and duration.',intro2:'The integration persists state before control.',intro3:'Partial or uncertain results remain visible.',control:'Control',schedule:'Schedule',state:'State',info:'Information',cameras:'Cameras',all:'All cameras',scope:'Scope',allScope:'Everything',main:'Recording',sub:'Detection',duration:'Duration in minutes',pause:'Enable privacy',resume:'Resume safely',noCameras:'No Frigate cameras were found.',schedules:'Privacy windows',noSchedules:'No schedules.',add:'Add schedule',edit:'Edit',save:'Save',cancel:'Cancel',remove:'Delete',label:'Label',start:'Start',end:'End',enabled:'Enabled',days:['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],currentState:'Backend-confirmed state',noActive:'No active privacy transitions.',lastVerified:'Last verified operation',noHistory:'No completed operations.',source:'Source',deadline:'Deadline',reason:'Reason',operation:'Operation',observed:'Verified',attempts:'Resume attempts',evidence:'Per-target evidence',architecture:'Security model',architectureText:'The card never controls cameras, switches, or HA configuration directly. Every read and mutation goes through admin-only integration WebSocket commands. The backend owns schedules and restart recovery.',support:'Enjoying Frigate Privacy?',supportText:'You can support continued development and testing.',saved:'Saved',failed:'The operation failed',close:'Close',snapshots:'Snapshots',detection:'Detection',soundHint:'Sound detection does not confirm microphone capture or listening.',actions:'Buttons and automations',actionHint:'Choose cameras, scope and duration under Control, then use the generated action in Home Assistant.',trustHint:'To enable privacy from an automation or physical button, first create an HA automation using the action below and your own trigger. Then open Settings → Devices & services → Frigate Privacy → Configure. Under Trusted automations and scripts, select only that automation and save. Until then, the automation cannot control privacy.',example:'Binding example',copy:'Copy',copied:'Copied',notificationSettings:'Notifications and trusted actions',buttonPause:'Pause button',buttonResume:'Resume button',scriptPause:'Pause script',scriptResume:'Resume script',automationPause:'Automation / physical-button action',sceneHelper:'Scene with a helper',sceneHint:'HA scenes store states. Add a Toggle helper, select its state in a scene, and trust the automation below. Choose your physical-button trigger in the HA editor.',video:'Video',recording:'Recording',soundDetection:'Sound detection',preview:'Preview in HA',statusOn:'On',statusOff:'Off',statusIdle:'Idle',statusUnavailable:'Unavailable',statusUnknown:'Unknown' },
      }; return strings[this._lang] || strings.en;
    }

    setConfig(config) { this._config = { ...config }; this._invalidatePeriods('discarded'); this._periodContextKey = this._periodContext(this._hass); this._updateUI(); }
    set hass(hass) {
      const identityChanged = !!this._hass && (this._connection !== (hass?.connection || null) || this._userId !== (hass?.user?.id || null) || this._declaredAdmin !== (hass?.user?.is_admin === true) || this._instanceId !== (hass?.config?.instance_id || null));
      const context = this._periodContext(hass);
      const changed = context !== this._periodContextKey || this._periodCallWS !== hass?.callWS || this._periodContextConnection !== hass?.connection;
      const authorityChanged = !!this._hass && this._declaredActive !== (hass?.user?.is_active !== false);
      this._hass = hass; this._instanceId = hass?.config?.instance_id || null; this._declaredActive = hass?.user?.is_active !== false;
      if (changed) this._invalidatePeriods('discarded');
      this._periodContextKey = context; this._periodCallWS = hass?.callWS; this._periodContextConnection = hass?.connection;
      if (identityChanged || authorityChanged || !hass) this._clearPrivateState();
      if (this._connection !== (hass?.connection || null)) this._periodConnectionOffline = hass?.connection?.connected === false;
      this._bindPeriodConnection();
      if (!hass) { this._connection = null; this._userId = null; this._permissionDenied = true; this._updateUI(); return; }
      this._lang = String(hass.language || 'en').startsWith('pl') ? 'pl' : 'en';
      this._connection = hass.connection || null; this._userId = hass.user?.id || null;
      this.classList.toggle('bento-dark', !!hass.themes?.darkMode); this._declaredAdmin = hass.user?.is_admin === true; if (identityChanged || authorityChanged || !this._integrationChecked) this._permissionDenied = !this._declaredAdmin || hass.user?.is_active === false;
      if (this._permissionDenied) { this._integrationChecked = true; this._integrationAvailable = false; this._updateUI(); return; }
      if (this._historyBrowserOnline && !this._periodConnectionOffline && !this._connectPromise && !this._busy && (!this._integrationChecked || Date.now() - this._lastStatePollAt >= 15000)) this._connectIntegration();
      this._updateUI();
    }
    disconnectedCallback() {
      if (this._countdownTimer) clearInterval(this._countdownTimer); this._countdownTimer = null;
      this._navigationObserver?.disconnect(); this._navigationObserver = null; this._pendingControlFocus = null;
      window.removeEventListener('offline', this._periodOffline); window.removeEventListener('online', this._periodOnline);
      if (this._periodBoundConnection?.removeEventListener) {
        this._periodBoundConnection.removeEventListener('disconnected', this._periodDisconnected);
        this._periodBoundConnection.removeEventListener('ready', this._periodReady);
      }
      this._periodBoundConnection = null;
      this._clearPrivateState(); this._invalidatePeriods('discarded'); this._updateUI();
      if (this._statePollTimer) clearInterval(this._statePollTimer); this._statePollTimer = null; this._requestEpoch += 1; this._connectPromise = null; this._lastStatePollAt = 0; this._busy = false; this._integrationChecked = false; this._integrationAvailable = false; if (this._toastTimer) clearTimeout(this._toastTimer); }
    _clearPrivateState() {
      this._notifications=null;this._notificationResult=null;this._notificationEpoch+=1;
      if(this._notificationTimer)clearTimeout(this._notificationTimer);this._notificationTimer=null;
      this._closePreview();
      this._cameraActions = Object.create(null);
      this._pendingControlFocus = null;
      this._invalidatePeriods('discarded');
      this.shadowRoot.activeElement?.blur(); this._busy = false; this._mutationOutcome = null; this._error = ''; this._editingScheduleIdx = null; this._scheduleForm = this._emptySchedule();
      if (this._toastTimer) clearTimeout(this._toastTimer);
      this._requestEpoch += 1; this._connectPromise = null; this._lastStatePollAt = 0; this._integrationChecked = false; this._integrationAvailable = false;
      this._cameras = []; this._schedules = []; this._paused = {}; this._lastOperations = {}; this._selectedCameras.clear(); this._periodProducerKey = null;
    }
    _denyAccess() { this._clearPrivateState(); this._permissionDenied = true; this._integrationChecked = true; this._updateUI(); }
    _emptySchedule() { return { enabled:true,days:[1,2,3,4,5],startHour:18,startMin:0,endHour:20,endMin:0,repeat:true,label:'' }; }
    async _callIntegration(command, payload = {}) {
      if (!this._hass || (this._hass.user?.is_admin !== true || this._hass.user?.is_active === false)) throw Object.assign(new Error('admin_required'), { code: 'unauthorized' });
      return this._hass.callWS({ type: `ha_frigate_privacy/${command}`, ...payload });
    }
    async _connectIntegration() {
      const epoch = ++this._requestEpoch; const refresh = this._integrationChecked && this._integrationAvailable; this._lastStatePollAt = Date.now(); if (!refresh) this._integrationChecked = false; this._error = '';
      this._connectPromise = this._callIntegration('get_state').then((state) => { if (epoch !== this._requestEpoch) return; this._permissionDenied = false; this._integrationAvailable = true; this._integrationChecked = true; this._applyState(state); })
        .catch((error) => { if (epoch !== this._requestEpoch) return; if (error?.code === 'unauthorized') { this._denyAccess(); return; } this._integrationAvailable = false; this._integrationChecked = true; this._invalidatePeriods('discarded'); this._error = this._safeError(error); })
        .finally(() => { if (epoch === this._requestEpoch) { this._connectPromise = null; this._updateUI(); } });
      this._updateUI(); return this._connectPromise;
    }
    _applyState(state) {
      const safe = state && typeof state === 'object' && !Array.isArray(state) ? state : {};
      const n=safe.notifications;
      this._notifications=n&&typeof n==='object'&&!Array.isArray(n)&&typeof n.destination==='string'&&typeof n.available==='boolean'?{destination:n.destination,label:typeof n.label==='string'?n.label:n.destination,available:n.available,events:n.events&&typeof n.events==='object'?n.events:{}}:null;
      const producerKey = JSON.stringify([safe.paused || {}, safe.last_operations || {}]);
      if (producerKey !== this._periodProducerKey && (this._periodInfo || this._periodWire)) this._invalidatePeriods('discarded');
      this._periodProducerKey = producerKey;
      this._recoveryReady = safe.recovery_ready !== false; this._cameras = Array.isArray(safe.cameras) ? safe.cameras : []; this._schedules = Array.isArray(safe.schedules) ? safe.schedules : []; const records = safe.paused && typeof safe.paused === 'object' && !Array.isArray(safe.paused) ? safe.paused : {}; const terminal = safe.last_operations && typeof safe.last_operations === 'object' && !Array.isArray(safe.last_operations) ? safe.last_operations : {}; this._paused = Object.fromEntries(Object.entries(records).filter(([,record]) => record && record.active !== false && record.phase !== 'active')); this._lastOperations = Object.fromEntries(Object.entries(terminal).filter(([,record]) => record && record.active === false && record.phase === 'active'));
      const valid = new Set(this._cameras.map((camera) => camera.camera_id)); this._selectedCameras = new Set([...this._selectedCameras].filter((id) => valid.has(id)));
      if (this._previewCamera && !this._previewAllowed(this._previewCamera)) this._closePreview();
      this._updateUI();
    }
    _safeError(error) {
      const messages = {
        replay_saturated:['Replay protection reached its safe limit. The integration blocked the change before controlling cameras.','Ochrona przed powtórzeniem operacji osiągnęła bezpieczny limit. Integracja zablokowała zmianę przed sterowaniem kamerami.'],
        replay_integrity:['Replay-protection integrity could not be verified. Controls remain safely blocked.','Nie można potwierdzić integralności ochrony operacji. Sterowanie pozostaje bezpiecznie zablokowane.'],
        storage_failed:['The state could not be saved durably. The integration does not treat the operation as complete.','Nie udało się trwale zapisać stanu. Integracja nie uznaje operacji za zakończoną.'],
        invalid_payload:['Check the action settings and try again.','Sprawdź ustawienia operacji i spróbuj ponownie.'],
        recovery_pending:['State recovery is pending. Wait before trying again.','Odzyskiwanie stanu trwa. Poczekaj przed ponowieniem.'],
        unauthorized:['Administrator permission is required.','Wymagane są uprawnienia administratora.'],
        operation_failed:['The operation could not be completed. Check the current state before retrying.','Nie udało się zakończyć operacji. Sprawdź bieżący stan przed ponowieniem.'],
        partial:['Only part of the operation was confirmed. Check the camera state before retrying.','Potwierdzono tylko część operacji. Sprawdź stan kamer przed ponowieniem.'],
        unconfirmed:['The change may have been applied, but its result could not be confirmed. Check the current state before retrying.','Zmiana mogła zostać wykonana, ale jej wyniku nie potwierdzono. Sprawdź bieżący stan przed ponowieniem.'],
        not_checked:['The operation is in progress. Its result has not been checked yet.','Operacja trwa. Jej wynik nie został jeszcze sprawdzony.'],
        success:['The operation and current state were confirmed.','Potwierdzono wykonanie operacji i bieżący stan.'],
        success_pause:['The requested pause for the selected cameras and the integration state were confirmed.','Potwierdzono żądaną pauzę wybranych kamer i stan integracji.'],
        success_resume:['The requested safe resume for the selected cameras and the integration state were confirmed.','Potwierdzono żądane bezpieczne wznowienie wybranych kamer i stan integracji.'],
        success_schedule_upsert:['The schedule was saved and confirmed in the current integration state.','Harmonogram zapisano i potwierdzono w bieżącym stanie integracji.'],
        success_schedule_delete:['Schedule deletion was confirmed in the current integration state.','Usunięcie harmonogramu potwierdzono w bieżącym stanie integracji.'],
      };
      const row = Object.hasOwn(messages, error?.code) ? messages[error.code] : messages.operation_failed;
      return row[this._lang === 'pl' ? 1 : 0];
    }
    _mutationResult(command, result, expectedIds) {
      const object = value => !!value && typeof value === 'object' && !Array.isArray(value);
      if (!object(result)) return 'unconfirmed';
      if (command === 'set_schedule') return 'unconfirmed'; // Confirmed separately against saved state.
      if (!['pause_camera','resume_camera'].includes(command)) return 'unconfirmed';
      const flag = command === 'pause_camera' ? 'paused' : 'resumed';
      const phase = command === 'pause_camera' ? 'paused' : 'active';
      const rows = Array.isArray(result.results) ? result.results : [];
      if (result.phase === 'partial' || rows.some(row => object(row) && row.phase === 'partial')) return 'partial';
      const validRows = rows.length > 0 && rows.every(row => object(row) && typeof row.camera_id === 'string' && row.camera_id.length > 0 && typeof row[flag] === 'boolean' && ['paused','active','partial','error','recovering','pausing','resuming'].includes(row.phase));
      if (validRows && rows.some(row => row[flag] === true && row.phase === phase) && rows.some(row => row[flag] !== true || row.phase !== phase)) return 'partial';
      if (result.ok === false && result.phase === 'error' && (!rows.length || validRows && rows.every(row => row[flag] === false))) return 'error';
      const ids = rows.map(row => row?.camera_id);
      const complete = expectedIds.length > 0 && ids.length === expectedIds.length && new Set(ids).size === ids.length && expectedIds.every(id => ids.includes(id));
      return result.ok === true && result.phase === phase && validRows && complete && rows.every(row => row[flag] === true && row.phase === phase) ? 'success' : 'unconfirmed';
    }
    _mutationReadback(command, payload, result, state, expectedIds) {
      const object = value => !!value && typeof value === 'object' && !Array.isArray(value);
      if (!object(state) || !Array.isArray(state.cameras) || !Array.isArray(state.schedules) || !object(state.paused)) return false;
      if (command === 'set_schedule') {
        if (!object(result) || result.ok === false || !state.schedules.every(object)) return false;
        if (payload.action === 'delete') return result.deleted === true && typeof payload.schedule_id === 'string' && !state.schedules.some(item => item.id === payload.schedule_id);
        if (payload.action !== 'upsert' || !object(result.schedule) || typeof result.schedule.id !== 'string' || !result.schedule.id || !object(payload.schedule)) return false;
        const fields = ['label','enabled','days','startHour','startMin','endHour','endMin','repeat'];
        const equal = (left,right) => fields.every(key => key === 'days' ? Array.isArray(left.days) && Array.isArray(right.days) && JSON.stringify([...left.days].sort()) === JSON.stringify([...right.days].sort()) : left[key] === right[key]);
        const requested = payload.schedule;
        if (requested.id && requested.id !== result.schedule.id || !equal(requested,result.schedule)) return false;
        const matches = state.schedules.filter(item => item.id === result.schedule.id);
        return matches.length === 1 && equal(matches[0],result.schedule);
      }
      const known = new Set(state.cameras.map(camera => camera?.camera_id));
      return expectedIds.length > 0 && expectedIds.every(id => known.has(id) && (command === 'pause_camera' ? object(state.paused[id]) && state.paused[id].phase === 'paused' && state.paused[id].active !== false : !state.paused[id] || state.paused[id].active === false || state.paused[id].phase === 'active'));
    }
    _buildMutationResult() {
      if (!this._mutationOutcome) return '';
      const ui = createUiV3({language:this._lang});
      return `<div class="notice" data-action-result role="status" style="margin-bottom:16px"><div>${ui.statusHtml(this._mutationOutcome.code)}<p>${_esc(this._safeError({code:this._mutationOutcome.reason}))}</p></div></div>`;
    }
    _newOperationId(action) { const random = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`; return `${action}-${random}`.slice(0, 128); }
    _cameraMutationResults(command,result,state,expectedIds) {
      const flag = command === 'pause_camera' ? 'paused' : 'resumed';
      const phase = command === 'pause_camera' ? 'paused' : 'active';
      const rows = Array.isArray(result?.results) ? result.results : [];
      return Object.fromEntries(expectedIds.map(id => {
        const matches = rows.filter(row=>row && typeof row==='object' && !Array.isArray(row) && row.camera_id===id);
        const row = matches.length===1 ? matches[0] : null;
        let code = 'unconfirmed';
        if (row && typeof row[flag]==='boolean') {
          if (row[flag]===true && row.phase===phase && this._mutationReadback(command,{},result,state,[id])) code='success';
          else if (row[flag]===false && row.phase==='error') code='error';
          else if (row[flag]===false && row.phase==='partial') code='partial';
        }
        return [id,code];
      }));
    }
    async _runMutation(command, payload = {}) {
      if (this._mutationWire || this._busy || !this._integrationAvailable || !this._recoveryReady) return false;
      const epoch = this._requestEpoch; const wire = {};
      const pausedIds = Object.keys(this._paused);
      const expectedIds = [...(payload.cameras?.length ? payload.cameras : command === 'resume_camera' && pausedIds.length ? pausedIds : this._cameras.map(camera => camera.camera_id))];
      if (command === 'pause_camera' || command === 'resume_camera') for (const id of expectedIds) this._cameraActions[id] = {pending:true,code:'not_checked'};
      this._mutationWire = wire; this._busy = true; this._error = ''; this._mutationOutcome = {code:'not_checked',reason:'not_checked'}; this._updateUI();
      let accepted = false; let outcome = 'unconfirmed'; let cameraResults = null;
      try {
        const result = await this._callIntegration(command, payload); accepted = true;
        if (epoch !== this._requestEpoch) return false;
        outcome = this._mutationResult(command, result, expectedIds);
        const nextState = await this._callIntegration('get_state');
        if (epoch !== this._requestEpoch) return false;
        const verified = this._mutationReadback(command, payload, result, nextState, expectedIds);
        if (command === 'pause_camera' || command === 'resume_camera') cameraResults = this._cameraMutationResults(command,result,nextState,expectedIds);
        if (command === 'set_schedule') outcome = verified ? 'success' : 'unconfirmed';
        else if (outcome === 'success' && !verified) outcome = 'unconfirmed';
        if (nextState && typeof nextState === 'object' && !Array.isArray(nextState) && Array.isArray(nextState.cameras) && Array.isArray(nextState.schedules) && nextState.paused && typeof nextState.paused === 'object' && !Array.isArray(nextState.paused)) this._applyState(nextState);
        const successReason = command === 'pause_camera' ? 'success_pause' : command === 'resume_camera' ? 'success_resume' : payload.action === 'delete' ? 'success_schedule_delete' : 'success_schedule_upsert';
        this._mutationOutcome = {code:outcome,reason:outcome === 'success' ? successReason : outcome === 'error' ? 'operation_failed' : outcome};
        this._error = outcome === 'success' ? '' : this._safeError({code:this._mutationOutcome.reason});
        this._showToast(outcome === 'success' ? this._t.saved : this._error, outcome);
        return outcome === 'success';
      } catch (error) {
        if (epoch !== this._requestEpoch) return false;
        if (error?.code === 'unauthorized') { this._denyAccess(); return false; }
        const rejected = !accepted && ['invalid_payload','replay_saturated','replay_integrity','recovery_pending'].includes(error?.code);
        const code = accepted && outcome === 'partial' ? outcome : rejected ? 'error' : 'unconfirmed';
        const reason = rejected || error?.code === 'storage_failed' ? error.code : code === 'error' ? 'operation_failed' : code;
        this._mutationOutcome = {code,reason}; this._error = this._safeError({code:reason}); this._showToast(this._error, code); return false;
      } finally {
        if (this._mutationWire === wire) this._mutationWire = null;
        if (epoch === this._requestEpoch) {
          this._busy = false;
          if (command === 'pause_camera' || command === 'resume_camera') for (const id of expectedIds) this._cameraActions[id] = {pending:false,code:cameraResults?.[id] || (this._mutationOutcome?.code==='error'?'error':'unconfirmed')};
        }
        this._updateUI();
      }
    }
    _selectedCameraIds() { if (!this._selectedCameras.size) return undefined; return this._cameras.filter((camera) => this._selectedCameras.has(camera.camera_id)).map((camera) => camera.camera_id); }
    _pause() { const minutes = Math.max(1, Math.min(1440, Number.parseInt(this._customMinutes, 10) || 30)); this._customMinutes = minutes; haToolsPersistence.save('ha-frigate-privacy-pause-minutes', minutes); const cameras = this._selectedCameraIds(); return this._runMutation('pause_camera', { ...(cameras ? { cameras } : {}), duration_minutes: minutes, stream_type: this._pauseStreamType, operation_id: this._newOperationId('pause') }); }
    _resume() { const cameras = this._selectedCameraIds(); return this._runMutation('resume_camera', { ...(cameras ? { cameras } : {}), operation_id: this._newOperationId('resume') }); }
    _retryResume(cameraId) { return this._runMutation('resume_camera', { cameras:[cameraId], operation_id:this._newOperationId('resume-retry') }); }
    async _saveScheduleFromForm() {
      const form = this._scheduleForm; const schedule = { id: form.id || this._newOperationId('schedule'), enabled:form.enabled !== false,days:[...form.days],startHour:Math.max(0,Math.min(23,Number.parseInt(form.startHour,10)||0)),startMin:Math.max(0,Math.min(59,Number.parseInt(form.startMin,10)||0)),endHour:Math.max(0,Math.min(23,Number.parseInt(form.endHour,10)||0)),endMin:Math.max(0,Math.min(59,Number.parseInt(form.endMin,10)||0)),repeat:form.repeat !== false,label:String(form.label||'').slice(0,120) };
      const saved = await this._runMutation('set_schedule', { action:'upsert', schedule, operation_id:this._newOperationId('schedule-upsert') }); if (!saved) return false; this._editingScheduleIdx = null; this._scheduleForm = this._emptySchedule(); this._updateUI(); return true;
    }
    _editSchedule(index) { const source = this._schedules[index]; if (!source) return; this._editingScheduleIdx = index; this._scheduleForm = { ...source, days:[...(source.days||[])] }; this._updateUI(); }
    _deleteSchedule(index) { const schedule = this._schedules[index]; if (!schedule?.id) return; return this._runMutation('set_schedule', { action:'delete', schedule_id:schedule.id, operation_id:this._newOperationId('schedule-delete') }); }
    _toggleSchedule(index) { const schedule = this._schedules[index]; if (!schedule) return; return this._runMutation('set_schedule', { action:'upsert', schedule:{ ...schedule, enabled:!schedule.enabled }, operation_id:this._newOperationId('schedule-toggle') }); }
    _phaseSummary() {
      if(this._permissionDenied)return{phase:'error',label:this._t.adminRequired};
      if(!this._integrationChecked)return{phase:'connecting',label:this._t.connecting};
      if(!this._integrationAvailable)return{phase:'error',label:this._t.unavailable};
      if(!this._recoveryReady)return{phase:'recovering',label:this._t.recovering};
      const records=Object.entries(this._paused||{});
      if(!records.length)return{phase:'active',label:this._t.online};
      const phase=['error','partial','resuming','pausing','paused'].find(candidate=>records.some(([,r])=>(r.phase||'paused')===candidate))||'paused';
      const matching=records.filter(([,r])=>(r.phase||'paused')===phase);
      const camera=matching.find(([id])=>this._cameras.some(c=>c.camera_id===id))?.[0];
      if(phase!=='partial'&&phase!=='error')return{phase,label:this._periodText(phase)};
      const format=this._formatUi(),count=format.count(matching.length,this._lang==='pl'?{one:'kamera',few:'kamery',many:'kamer',other:'kamery'}:{one:'camera',other:'cameras'});
      return{phase,camera,label:`${count}: ${this._lang==='pl'?(phase==='partial'?'wynik częściowy':'błąd'):(phase==='partial'?'partial result':'error')}`};
    }
    _formatUi() { return createFormatUi.forHass(this._hass); }
    _cameraDeadline(record,format=this._formatUi()) {
      const end=typeof record?.ends_at==='string'?Date.parse(record.ends_at):NaN;
      if(!Number.isFinite(end))return record?.ends_at===null?this._cameraStrings().untimed:this._cameraStrings().invalid;
      const label=(format.date(end)===format.date(Date.now())?'':format.date(end,true)+' ')+format.clock(end);
      return `${this._lang==='pl'?'Prywatność do':'Privacy until'} ${label}`;
    }
    _cameraProgress(record) {
      const start=typeof record?.started_at==='string'?Date.parse(record.started_at):NaN;
      const end=typeof record?.ends_at==='string'?Date.parse(record.ends_at):NaN;
      return Number.isFinite(start)&&Number.isFinite(end)&&end>start?Math.max(0,Math.min(100,(Date.now()-start)/(end-start)*100)):null;
    }
    _buildIntroBanner() {
      if (haToolsPersistence.loadSync('ha-intro-dismissed-ha-frigate-privacy') === '1') return ''; const t = this._t;
      return `<div class="intro-banner" data-intro="ha-frigate-privacy"><button class="intro-dismiss" data-action="dismiss-intro" aria-label="${_esc(t.close)}"><ha-icon icon="mdi:close"></ha-icon></button><div class="intro-headline"><ha-icon icon="mdi:shield-lock-outline"></ha-icon>${_esc(t.introTitle)}</div><ol class="intro-steps"><li>${_esc(t.intro1)}</li><li>${_esc(t.intro2)}</li><li>${_esc(t.intro3)}</li></ol></div>`;
    }
    _dismissIntro() { haToolsPersistence.save('ha-intro-dismissed-ha-frigate-privacy', '1'); this._lastHtml = ''; this._updateUI(); }
    _buildDonateFooter() { if (!this._hass?.user?.is_admin || this._config.show_support === false || haToolsPersistence.loadSync("ha-frigate-privacy-support-dismissed") === "1") return ""; const t=this._t; return `<div class="donate-section" data-source="ha-frigate-privacy"><a class="donate-btn" href="https://buymeacoffee.com/macsiem" target="_blank" rel="noopener noreferrer">${_esc(t.support)}</a><button type="button" data-action="dismiss-support" aria-label="${_esc(this._lang === 'pl' ? 'Ukryj link wsparcia' : 'Dismiss support link')}">×</button></div>`; }
    _dismissSupport() { haToolsPersistence.save("ha-frigate-privacy-support-dismissed", "1"); this._lastHtml = ""; this._updateUI(); }
    _buildGate() { const t=this._t; if(!this._integrationChecked)return `<div class="notice"><ha-icon icon="mdi:progress-clock"></ha-icon><div><h3>${_esc(t.connecting)}</h3><p>${_esc(t.subtitle)}</p></div></div>`; if(this._permissionDenied)return `<div class="notice error"><ha-icon icon="mdi:account-lock-outline"></ha-icon><div><h3>${_esc(t.adminRequired)}</h3><p>${_esc(t.adminHint)}</p><button class="btn btn-secondary" data-action="retry">${_esc(t.retry)}</button></div></div>`; if(!this._integrationAvailable)return `<div class="notice error"><ha-icon icon="mdi:lan-disconnect"></ha-icon><div><h3>${_esc(t.unavailable)}</h3><p>${_esc(t.unavailableHint)}</p><button class="btn btn-secondary" data-action="retry" style="margin-top:12px">${_esc(t.retry)}</button></div></div>`; if(!this._recoveryReady)return `<div class="notice"><ha-icon icon="mdi:shield-sync-outline"></ha-icon><div><h3>${_esc(t.recovering)}</h3><p>${_esc(t.recoveringHint)}</p></div></div>`; return ''; }
    _cameraStrings() {
      return this._lang === 'pl'
        ? {remaining:'Pozostało',awaiting:'Termin minął — oczekiwanie na backend',untimed:'Bez terminu automatycznego wznowienia',invalid:'Termin niepotwierdzony',duration:'Zastosowany czas',scope:'Zastosowany zakres',pending:'Trwa stosowanie — wynik niepotwierdzony',preview:'Podgląd',hide:'Zwiń podgląd',loading:'Ładowanie podglądu HA…',failed:'Podgląd HA jest niedostępny. Zwiń i spróbuj ponownie.',hint:'Podgląd HA na żądanie. Sam obraz nie potwierdza stanu prywatności.'}
        : {remaining:'Remaining',awaiting:'Deadline reached — awaiting backend',untimed:'No automatic resume deadline',invalid:'Deadline unconfirmed',duration:'Applied duration',scope:'Applied scope',pending:'Applying — result unconfirmed',preview:'Preview',hide:'Close preview',loading:'Loading HA preview…',failed:'HA preview is unavailable. Close and try again.',hint:'HA preview on demand. An image alone does not confirm privacy.'};
    }
    _countdownText(record) {
      const t=this._cameraStrings();
      if(record?.ends_at===null)return t.untimed;
      const end=typeof record?.ends_at==='string'?Date.parse(record.ends_at):NaN;
      if(!Number.isFinite(end))return t.invalid;
      const minutes=Math.ceil((end-Date.now())/60000);
      if(minutes<=0)return t.awaiting;
      const format=this._formatUi(),hours=Math.floor(minutes/60),rest=minutes%60;
      const value=hours?`${format.number(hours)} ${this._lang==='pl'?'godz.':'h'}${rest?' '+format.number(rest)+' min':''}`:`${format.number(minutes)} min`;
      return `${t.remaining}: ${value}`;
    }
    _tickCountdowns() {
      // Text/progress only: retain controls, their focus and any running preview.
      if(!this.isConnected||!this._periodAuthority())return;
      const format=this._formatUi();
      for(const node of this.shadowRoot.querySelectorAll('[data-camera-countdown]')) {
        const record=this._ownCameraRecord(this._paused,node.dataset.cameraCountdown);
        if(record)node.textContent=this._countdownText(record);
      }
      for(const node of this.shadowRoot.querySelectorAll('[data-camera-deadline]')) {
        const record=this._ownCameraRecord(this._paused,node.dataset.cameraDeadline);
        if(record)node.textContent=this._cameraDeadline(record,format);
      }
      for(const node of this.shadowRoot.querySelectorAll('[data-camera-progress]')) {
        const record=this._ownCameraRecord(this._paused,node.dataset.cameraProgress),value=this._cameraProgress(record);
        if(value!==null)node.value=value;
      }
    }
    _ownCameraRecord(records, id) {
      if (!records || typeof records !== 'object' || !Object.hasOwn(records, id)) return null;
      const record = records[id];
      return record && typeof record === 'object' && !Array.isArray(record) ? record : null;
    }
    _cameraFeedback(cam) {
      const activeRecord = this._ownCameraRecord(this._paused, cam.camera_id);
      const record = activeRecord || this._ownCameraRecord(this._lastOperations, cam.camera_id);
      const t = this._t, labels = this._cameraStrings();
      const attempt = this._ownCameraRecord(this._cameraActions, cam.camera_id);
      const request = attempt ? `<div class="helper" ${attempt.pending ? 'data-camera-pending' : ''}>${_esc(this._lang==='pl'?'Ostatnie żądanie':'Last request')}: ${attempt.pending ? _esc(labels.pending) : createUiV3({language:this._lang}).statusHtml(attempt.code)}</div>` : '';
      if (!record) return request ? `<div class="camera-feedback" data-camera-feedback="${_esc(cam.camera_id)}">${request}</div>` : '';
      const phase = ['pausing','paused','resuming','partial','error','active'].includes(record.phase) ? record.phase : 'unknown';
      const scope = {all:t.allScope,main:t.main,sub:t.sub}[record.stream_type] || t.statusUnknown;
      const start = typeof record.started_at === 'string' ? Date.parse(record.started_at) : NaN;
      const end = typeof record.ends_at === 'string' ? Date.parse(record.ends_at) : NaN;
      const minutes = Number.isFinite(start) && Number.isFinite(end) && end > start ? Math.round((end-start)/60000) : null;
      const pauseLabel = this._lang==='pl'?'Pauza':'Pause', resumeLabel = this._lang==='pl'?'Wznowienie':'Resume';
      const evidence = [
        ...(activeRecord ? [`${t.deadline}: ${this._formatCameraTime(record.ends_at)}`, `UTC: ${record.started_at || '—'} → ${record.ends_at || '—'}`] : []),
        ...Object.entries(record.target_outcomes || {}).map(([target,value])=>`${pauseLabel} · ${target}: ${String(value)}`),
        ...Object.entries(record.resume_target_outcomes || {}).map(([target,value])=>`${resumeLabel} · ${target}: ${String(value)}`),
        ...Object.entries(record.last_verified_actual_state || {}).map(([target,value])=>`${t.observed} · ${target}: ${String(value)}`),
      ];
      // An extension keeps the original request's stream_type and may replace
      // camera_planned while preserving proof that the original action stopped video.
      const cameraEntity = record.camera_entity_id || cam.entity_id;
      const videoStopped = cam.camera_state==='off' || (record.camera_toggled===true &&
        record.target_outcomes?.[cameraEntity]==='paused' &&
        ['off','idle'].includes(record.last_verified_actual_state?.[cameraEntity]) && cam.camera_state==='idle');
      const videoUnconfirmed = phase==='paused' && record.stream_type==='all' && record.camera_planned!==true && !videoStopped;
      const scopeLabel = phase==='paused' && !videoUnconfirmed && record.extension!==true ? labels.scope : (this._lang==='pl'?'Żądany zakres':'Requested scope');
      const scheduleNote = record.extension===true ? `<div class="helper" data-schedule-coverage>${_esc(this._lang==='pl'
        ? 'Rozszerzenie harmonogramem: potwierdzone cele w dowodach poniżej.'
        : 'Schedule extension: see evidence below for confirmed targets.')}</div>` : '';
      const videoNote = videoUnconfirmed ? `<div class="helper" data-video-stop-unconfirmed>${_esc(this._lang==='pl'
        ? record.camera_toggled===true ? 'Bieżące dowody nie potwierdzają zatrzymania obrazu kamery.' : 'W tej operacji nie przełączano obrazu kamery. Wynik dotyczy przełączników Frigate; zatrzymanie obrazu nie jest potwierdzone.'
        : record.camera_toggled===true ? 'Camera video stop is not confirmed by current evidence.' : 'Camera video was not switched by this action. The result covers Frigate switches; video stop is not confirmed.')}</div>` : '';
      return `<div class="camera-feedback" data-camera-feedback="${_esc(cam.camera_id)}">${request}<span class="phase ${phase}" data-camera-phase="${phase}">${_esc(this._periodText(phase))}</span><div class="helper">${_esc(scopeLabel)}: ${_esc(scope)}${minutes !== null ? ` · ${_esc(this._lang==='pl'?'Czas timera':'Timer duration')}: ${minutes} min` : ''}</div>${scheduleNote}${videoNote}${activeRecord ? `<div class="camera-deadline-row"><span class="helper" data-camera-deadline="${_esc(cam.camera_id)}">${_esc(this._cameraDeadline(record))}</span><span class="camera-countdown" data-camera-countdown="${_esc(cam.camera_id)}" role="timer"></span></div>${this._cameraProgress(record)!==null?`<progress class="camera-progress" data-camera-progress="${_esc(cam.camera_id)}" max="100" value="0" aria-label="${_esc(this._lang==='pl'?'Upływ zaplanowanego czasu':'Planned time elapsed')}"></progress>`:''}` : ''}${evidence.length ? `<details class="evidence"><summary>${_esc(t.evidence)}</summary><div class="evidence-list">${evidence.map(text=>`<div>${_esc(text)}</div>`).join('')}</div></details>` : ''}</div>`;
    }
    _formatCameraTime(value) {
      const format=this._formatUi();return (format.pointLabel(value)||this._periodStrings().unknown)+' · '+format.timeZone;
    }
    _channelBadge(channel,label,values,icon) {
      const normalized = {streaming:'on',recording:'on',on:'on',off:'off',idle:'idle',unavailable:'unavailable'};
      const known = value => typeof value==='string' && Object.hasOwn(normalized,value) ? normalized[value] : 'unknown';
      const states = values.length ? [...new Set(values.map(known))] : ['unknown'];
      const state = states.length === 1 ? states[0] : 'mixed';
      const names = {on:this._t.statusOn,off:this._t.statusOff,idle:this._t.statusIdle,unavailable:this._t.statusUnavailable,unknown:this._t.statusUnknown};
      return `<span class="channel-badge" data-channel="${channel}" data-channel-state="${state}"><ha-icon icon="${icon}"></ha-icon>${_esc(label)}: ${_esc(states.map(s=>names[s]).join(' / '))}</span>`;
    }
    _cameraTile(cam) {
      const selected = this._selectedCameras.has(cam.camera_id), t = this._t, p = this._cameraStrings();
      const values = suffixes => (cam.switches || []).filter(item=>suffixes.includes(item.suffix)).map(item=>item.state);
      const expanded = this._previewCamera === cam.entity_id;
      const validEntity = typeof cam.entity_id === 'string' && /^camera\.[a-z0-9_]+$/.test(cam.entity_id);
      return `<div class="camera-tile"><div class="camera-card ${selected?'selected':''}" data-camera="${_esc(cam.camera_id)}" role="button" tabindex="0" aria-pressed="${selected}" aria-label="Camera: ${_esc(this._repairMojibake(cam.name))}"><ha-icon icon="mdi:cctv"></ha-icon><span class="camera-name">${_esc(this._repairMojibake(cam.name))}</span>${selected?'<ha-icon class="camera-check" icon="mdi:check-circle"></ha-icon>':''}</div><div class="channel-status">${this._channelBadge('video',t.video,[cam.camera_state],'mdi:video-outline')}${this._channelBadge('recording',t.recording,values(['_recordings']),'mdi:record-rec')}${this._channelBadge('snapshots',t.snapshots,values(['_snapshots']),'mdi:camera-outline')}${this._channelBadge('detection',t.detection,values(['_detect']),'mdi:motion-sensor')}${this._channelBadge('sound',t.soundDetection,values(['_audio_detection','_audio']),'mdi:microphone-outline')}</div>${this._cameraFeedback(cam)}${validEntity?`<button class="preview-btn" data-preview-camera="${_esc(cam.entity_id)}" aria-expanded="${expanded}" aria-controls="preview-${_esc(cam.camera_id)}">${_esc(expanded?p.hide:p.preview)}</button>${expanded?`<div id="preview-${_esc(cam.camera_id)}" class="camera-preview"><div data-preview-host="${_esc(cam.entity_id)}" role="region" aria-label="${_esc(p.preview+' · '+cam.name)}"><p class="helper">${_esc(p.loading)}</p></div><p class="helper">${_esc(p.hint)}</p></div>`:''}`:''}</div>`;
    }
    _previewAllowed(entity) {
      return this._periodAuthority() && this._integrationAvailable && this._recoveryReady &&
        typeof entity === 'string' && /^camera\.[a-z0-9_]+$/.test(entity) && this._cameras.some(cam=>cam.entity_id===entity);
    }
    _closePreview() {
      this._previewEpoch += 1; this._previewCamera = null; this._previewLoad = null;
      this._previewFailed = false;
      this._previewNode?.remove(); this._previewNode = null;
    }
    _togglePreview(entity) {
      const same = this._previewCamera === entity;
      this._closePreview();
      if (!same && this._previewAllowed(entity)) this._previewCamera = entity;
      this._updateUI();
    }
    _previewWait(promise) {
      // A stalled frontend import must leave an explicit retryable result.
      let timer;
      return Promise.race([promise, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('preview_unavailable')), 10000);
      })]).finally(() => clearTimeout(timer));
    }
    async _loadPreviewHelpers() {
      if (typeof window.loadCardHelpers !== 'function') {
        if (!this._previewBootstrap) {
          this._previewBootstrap = (async () => {
            await this._previewWait(customElements.whenDefined('partial-panel-resolver'));
            // HA's own route loader imports Lovelace without mounting a dashboard.
            // Feature detection covers current HA and the declared 2024.7 minimum.
            const resolver = document.createElement('partial-panel-resolver');
            const getRoutes = resolver._getRoutes || resolver.getRoutes;
            if (typeof getRoutes !== 'function') throw new Error('preview_unavailable');
            const path = 'ha-frigate-privacy-preview';
            const route = getRoutes.call(resolver, [{component_name:'lovelace',url_path:path}])?.routes?.[path];
            if (typeof route?.load !== 'function') throw new Error('preview_unavailable');
            await this._previewWait(route.load());
            if (typeof window.loadCardHelpers !== 'function') throw new Error('preview_unavailable');
          })().finally(() => { this._previewBootstrap = null; });
        }
        await this._previewBootstrap;
      }
      const helpers = await this._previewWait(window.loadCardHelpers());
      if (typeof helpers?.createCardElement !== 'function') throw new Error('preview_unavailable');
      return helpers;
    }
    async _syncPreview() {
      const entity = this._previewCamera, host = this.shadowRoot.querySelector('[data-preview-host]');
      if (!entity || !host || !this._previewAllowed(entity)) return;
      if (this._previewFailed) { host.textContent = this._cameraStrings().failed; return; }
      if (this._previewNode) { if (this._previewNode.parentNode !== host) host.replaceChildren(this._previewNode); this._previewNode.hass = this._hass; return; }
      if (this._previewLoad) return;
      const epoch = this._previewEpoch, wire = {}; this._previewLoad = wire;
      const current = () => epoch === this._previewEpoch && this._previewCamera === entity && this._previewAllowed(entity) && !!this.shadowRoot.querySelector('[data-preview-host]');
      try {
        const helpers = await this._loadPreviewHelpers();
        if (!current()) return;
        // Native HA card owns authentication and stream lifecycle. No external camera URLs or secrets.
        const node = await helpers.createCardElement({type:'picture-entity',entity,camera_view:'live',show_name:false,show_state:false,tap_action:{action:'none'},hold_action:{action:'none'},double_tap_action:{action:'none'}});
        if (!current()) { node?.remove(); return; }
        if (node?.localName !== 'hui-picture-entity-card') throw new Error('preview_unavailable');
        // createCardElement starts the lazy import but can return before upgrade.
        await this._previewWait(customElements.whenDefined(node.localName));
        if (!current()) { node.remove(); return; }
        customElements.upgrade(node);
        if (typeof node.setConfig !== 'function') throw new Error('preview_unavailable');
        node.hass = this._hass; this._previewNode = node;
        this.shadowRoot.querySelector('[data-preview-host]').replaceChildren(node);
      } catch (_) {
        if (current()) { this._previewFailed = true; this.shadowRoot.querySelector('[data-preview-host]').textContent = this._cameraStrings().failed; }
      } finally { if (this._previewLoad === wire) this._previewLoad = null; }
    }
    _buildControlTab() {
      const t=this._t;
      const lists=createListUi(this._hass?.language||this._lang);const cameras=[...this._cameras].sort((a,b)=>lists.compare(a.name,b.name)||lists.compare(a.camera_id,b.camera_id)).map(cam=>this._cameraTile(cam)).join('');
      const allSelected=this._selectedCameras.size===0; const phases=Object.values(this._paused||{});
      return `<div class="section"><div class="section-head"><h3>${_esc(t.cameras)}</h3><span class="helper">${this._cameras.length}</span></div><div class="camera-grid"><div class="camera-card ${allSelected?'selected':''}" data-camera="__all__" role="button" tabindex="0" aria-pressed="${allSelected}"><ha-icon icon="mdi:camera-outline"></ha-icon><span class="camera-name">${_esc(t.all)}</span>${allSelected?'<ha-icon class="camera-check" icon="mdi:check-circle"></ha-icon>':''}</div>${cameras||`<div class="empty">${_esc(t.noCameras)}</div>`}</div><p class="helper channel-hint">${_esc(t.soundHint)}</p></div>
      <div class="section"><div class="section-head"><h3>${_esc(t.scope)}</h3></div><div class="seg" role="radiogroup">${[['all',t.allScope],['main',t.main],['sub',t.sub]].map(([value,label])=>`<button class="seg-item ${this._pauseStreamType===value?'selected':''}" data-scope="${value}" role="radio" aria-checked="${this._pauseStreamType===value}">${_esc(label)}</button>`).join('')}</div><div class="duration-row"><input class="input-minutes" type="number" min="1" max="1440" value="${_esc(this._customMinutes)}" aria-label="${_esc(t.duration)}"><button class="btn btn-primary" data-action="pause-custom" ${this._busy||this._mutationWire||!this._cameras.length?'disabled':''}>${_esc(t.pause)}</button></div>${phases.length?`<button class="btn btn-danger btn-full" data-action="resume" ${this._busy||this._mutationWire?'disabled':''}>${_esc(t.resume)}</button>`:''}</div>`;
    }
    _buildScheduleTab() {
      const t=this._t; const list=this._schedules.map((schedule,index)=>{const days=[...(schedule.days||[])].sort().map((day)=>t.days[day-1]).filter(Boolean).join(', ');const time=`${String(schedule.startHour).padStart(2,'0')}:${String(schedule.startMin).padStart(2,'0')} – ${String(schedule.endHour).padStart(2,'0')}:${String(schedule.endMin).padStart(2,'0')}`;return `<div class="schedule-item"><div><div class="schedule-title">${_esc(schedule.label||t.schedule)}</div><div class="schedule-meta">${_esc(days)} · ${_esc(time)} · ${_esc(schedule.enabled?t.enabled:t.cancel)}</div></div><div class="schedule-actions"><button class="icon-btn" ${this._busy||this._mutationWire?'disabled':''} data-schedule-toggle="${index}" data-schedule-id="${_esc(schedule.id)}" aria-label="${_esc(t.enabled)}"><ha-icon icon="mdi:${schedule.enabled?'toggle-switch':'toggle-switch-off-outline'}"></ha-icon></button><button class="icon-btn" data-schedule-edit="${index}" data-schedule-id="${_esc(schedule.id)}" aria-label="${_esc(t.edit)}"><ha-icon icon="mdi:pencil-outline"></ha-icon></button><button class="icon-btn" ${this._busy||this._mutationWire?'disabled':''} data-schedule-delete="${index}" data-schedule-id="${_esc(schedule.id)}" aria-label="${_esc(t.remove)}"><ha-icon icon="mdi:delete-outline"></ha-icon></button></div></div>`;}).join(''); const form=this._scheduleForm;
      return `<p class="helper" data-schedule-zone>${_esc(this._lang==='pl'?'Harmonogram działa w strefie Home Assistant:':'Schedule uses the Home Assistant time zone:')} ${_esc(this._hass?.config?.time_zone||'UTC')}</p><div class="section"><div class="section-head"><h3>${_esc(t.schedules)}</h3><span class="helper">${this._schedules.length}</span></div><div class="schedule-list">${list||`<div class="empty">${_esc(t.noSchedules)}</div>`}</div></div><div class="section"><div class="section-head"><h3>${_esc(this._editingScheduleIdx==null?t.add:t.edit)}</h3></div><div class="form-grid"><div class="field field-wide"><label>${_esc(t.label)}</label><input class="input-label" aria-label="${_esc(t.label)}" maxlength="120" value="${_esc(form.label)}"></div><div class="field"><label>${_esc(t.start)}</label><input class="input-start" aria-label="${_esc(t.start)}" type="time" value="${_esc(`${String(form.startHour).padStart(2,'0')}:${String(form.startMin).padStart(2,'0')}`)}"></div><div class="field"><label>${_esc(t.end)}</label><input class="input-end" aria-label="${_esc(t.end)}" type="time" value="${_esc(`${String(form.endHour).padStart(2,'0')}:${String(form.endMin).padStart(2,'0')}`)}"></div><div class="field field-wide"><label>${_esc(t.schedule)}</label><div class="days">${t.days.map((label,index)=>`<button class="day-btn ${form.days.includes(index+1)?'selected':''}" data-day="${index+1}" aria-pressed="${form.days.includes(index+1)}" type="button">${_esc(label)}</button>`).join('')}</div></div></div><div class="form-actions"><button class="btn btn-primary" data-action="save-schedule" ${this._busy||this._mutationWire||!form.days.length?'disabled':''}>${_esc(t.save)}</button>${this._editingScheduleIdx==null?'':`<button class="btn btn-secondary" data-action="cancel-edit">${_esc(t.cancel)}</button>`}</div></div>`;
    }
    _buildStateTab() { const t=this._t; const render=(records,terminal=false)=>Object.entries(records||{}).map(([cameraId,state])=>{const outcomes=state.target_outcomes&&typeof state.target_outcomes==='object'?Object.entries(state.target_outcomes):[];const resumeOutcomes=state.resume_target_outcomes&&typeof state.resume_target_outcomes==='object'?Object.entries(state.resume_target_outcomes):[];const actual=state.last_verified_actual_state&&typeof state.last_verified_actual_state==='object'?Object.entries(state.last_verified_actual_state):[];const evidence=[...outcomes.map(([target,value])=>`${target}: ${value}`),...resumeOutcomes.map(([target,value])=>`${target}: ${value}`),...actual.map(([target,value])=>`${target}: actual=${value??'missing'}`)];const retry=!terminal&&(['error','partial'].includes(state.phase)||state.resume_blocked);return `<div class="state-row"><div><div class="state-name">${_esc(state.name||cameraId)}</div><div class="state-meta">${_esc(t.source)}: ${_esc(state.source||'unknown')} · ${_esc(t.deadline)}: ${_esc(this._formatCameraTime(state.ends_at))}<br>${_esc(t.operation)}: ${_esc(state.resume_operation_id||state.operation_id||'—')}<br>${_esc(t.observed)}: ${_esc(this._formatCameraTime(state.observed_at))} · ${_esc(t.attempts)}: ${_esc(state.resume_attempt_count||0)}${state.reason?`<br>${_esc(t.reason)}: ${_esc(state.reason)}`:''}</div></div><span class="phase ${_esc(state.phase||'paused')}">${_esc(this._periodText(state.phase||'paused'))}</span>${evidence.length?`<details class="evidence"><summary>${_esc(t.evidence)}</summary><div class="evidence-list">${evidence.map((item)=>`<div>${_esc(item)}</div>`).join('')}</div></details>`:''}${retry?`<div class="state-actions"><button class="btn btn-secondary" data-retry-camera="${_esc(cameraId)}" ${this._busy||this._mutationWire?'disabled':''}>${_esc(t.retryResume)}</button></div>`:''}</div>`;}).join('');const activeRows=render(this._paused);const terminalRows=render(this._lastOperations,true);return `<div class="section"><div class="section-head"><h3>${_esc(t.currentState)}</h3></div><div class="state-grid">${activeRows||`<div class="empty">${_esc(t.noActive)}</div>`}</div></div><div class="section"><div class="section-head"><h3>${_esc(t.lastVerified)}</h3></div><div class="state-grid">${terminalRows||`<div class="empty">${_esc(t.noHistory)}</div>`}</div></div>`; }
    _periodAuthority() {
      return this.isConnected && this._hass?.user?.is_admin === true && this._hass.user.is_active !== false &&
        !this._permissionDenied && this._historyBrowserOnline && !this._periodConnectionOffline &&
        this._hass.connection?.connected !== false && typeof this._hass.callWS === 'function';
    }
    _periodContext(hass) {
      const user = hass?.user || {};
      const groups = Array.isArray(user.groups) ? user.groups.map(group => String(group?.id || '')).sort() : [];
      return JSON.stringify([hass?.config?.instance_id || null, user.id || null, user.is_admin === true, user.is_active !== false, groups,
        Array.isArray(user.group_ids) ? user.group_ids.map(String).sort() : [],
        hass?.language || 'en', hass?.config?.time_zone || 'UTC', hass?.connection?.connected !== false, this._periodDays, this._config]);
    }
    _invalidatePeriods(state = 'discarded') {
      this._periodEpoch += 1;
      if (this._periodDeadline) clearTimeout(this._periodDeadline);
      this._periodDeadline = null; this._periods = []; this._periodInfo = null;
      this._periodSelected = null; this._periodPage = 0; this._periodState = state;
      // Never release an occupied HA callWS wire before its actual settlement.
      const panel = this.shadowRoot.querySelector('.history-panel');
      if (panel) { panel.replaceChildren(); this._lastHtml = ''; }
    }
    _bindPeriodConnection() {
      const next = this._hass?.connection || null;
      if (this._periodBoundConnection === next) return;
      if (this._periodBoundConnection?.removeEventListener) {
        this._periodBoundConnection.removeEventListener('disconnected', this._periodDisconnected);
        this._periodBoundConnection.removeEventListener('ready', this._periodReady);
      }
      this._periodBoundConnection = next;
      if (this.isConnected && next?.addEventListener) {
        next.addEventListener('disconnected', this._periodDisconnected);
        next.addEventListener('ready', this._periodReady);
      } else this._periodBoundConnection = null;
    }
    _periodDeadlineExpired() {
      this._invalidatePeriods('timeout'); this._updateUI();
    }
    _setPeriodRange(value) {
      const days = Number(value);
      if (![7, 30].includes(days) || days === this._periodDays) return;
      this._periodDays = days; this._invalidatePeriods('discarded');
      this._periodContextKey = this._periodContext(this._hass); this._updateUI();
    }
    async _refreshPeriods() {
      if (this._periodWire || !this._periodAuthority()) return false;
      this._invalidatePeriods('loading');
      const epoch = this._periodEpoch; const hass = this._hass;
      const context = this._periodContext(hass); const connection = hass.connection;
      const callWS = hass.callWS; const wire = {};
      this._periodWire = wire;
      this._periodDeadline = setTimeout(() => this._periodDeadlineExpired(), 15000);
      this._updateUI();
      const current = () => epoch === this._periodEpoch && this._periodAuthority() &&
        this._hass?.connection === connection && this._hass?.callWS === callWS && this._periodContext(this._hass) === context;
      try {
        const payload = await callWS.call(hass, { type:'ha_frigate_privacy/get_periods', days:this._periodDays });
        if (!current()) return false;
        const projection = this._validatePeriods(payload);
        this._periods = projection.rows; this._periodInfo = projection.info;
        this._periodSelected = this._periods[0]?.id || null; this._periodState = 'ready';
        return true;
      } catch (error) {
        if (!current()) return false;
        if (error?.code === 'unauthorized') { this._denyAccess(); return false; }
        this._invalidatePeriods('error'); return false;
      } finally {
        if (this._periodWire === wire) this._periodWire = null;
        if (epoch === this._periodEpoch && this._periodDeadline) clearTimeout(this._periodDeadline);
        if (epoch === this._periodEpoch) this._periodDeadline = null;
        this._updateUI();
      }
    }
    _validatePeriods(payload) {
      const phases = ['pausing','paused','resuming','partial','error','active'];
      const reasons = ['pause_incomplete','manual_override','admin_request','schedule_window_ended','manual_deadline_elapsed','restart_recovery','restart_during_pause','recovery_targets_missing','switch_unavailable','resume_failed','resume_cancelled','state_persistence_failed','invalid_persisted_targets','invalid_persisted_state','recovery_pending','unknown'];
      const outcomes = ['pending','missing','unavailable','preexisting_off','paused','active','service_failed','readback_failed','failed','repaused','re_pause_readback_failed','re_pause_cancelled','re_pause_service_failed','unknown'];
      const states = ['on','off','idle','streaming','recording','unavailable','unknown'];
      const knownChannels = ['detection','recording','snapshots','sound_detection','motion','camera_control'];
      const date = value => value === null || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,19) === value.slice(0,19));
      const fail = () => { throw new Error('invalid_history'); };
      if (!payload || payload.schema !== 1 || !['ready','legacy_latest','corrupt','unsupported','unavailable'].includes(payload.status) || !Array.isArray(payload.periods) || payload.periods.length > 200) fail();
      const ids = new Set();
      const rows = payload.periods.map(row => {
        if (!row || typeof row.id !== 'string' || !/^[a-f0-9]{64}$/.test(row.id) || ids.has(row.id) || typeof row.camera_id !== 'string' || !/^[a-z0-9_]{1,255}$/.test(row.camera_id)) fail();
        ids.add(row.id);
        if (row.generation !== null && (!Number.isSafeInteger(row.generation) || row.generation < 0)) fail();
        for (const field of ['started_at','ended_at','planned_ends_at','observed_at']) if (!date(row[field])) fail();
        if (!phases.includes(row.phase) || !['manual','schedule','unknown'].includes(row.source) || typeof row.verified_restore !== 'boolean' || row.evidence_scope !== 'transition_intent') fail();
        for (const field of ['reason','end_reason']) if (row[field] !== null && !reasons.includes(row[field])) fail();
        const elapsed = row.started_at && row.ended_at ? (Date.parse(row.ended_at)-Date.parse(row.started_at))/1000 : null;
        if ((elapsed !== null && elapsed < 0) || (elapsed === null ? row.duration_seconds !== null : typeof row.duration_seconds !== 'number' || !Number.isFinite(row.duration_seconds) || Math.abs(row.duration_seconds-elapsed) > .001) || (row.verified_restore && (!row.ended_at || row.phase !== 'active' || row.end_reason === 'manual_override'))) fail();
        const channels = field => {
          if (!Array.isArray(row[field]) || row[field].length > 256) fail();
          return Object.freeze(row[field].map(item => {
            if (!item || typeof item.target !== 'string' || !/^(switch|camera)\.[a-z0-9_]{1,255}$/.test(item.target) || !(field === 'channels' ? knownChannels : ['unknown']).includes(item.channel) || !outcomes.includes(item.pause_outcome) || !outcomes.includes(item.restore_outcome) || !states.includes(item.observed_state)) fail();
            if (item.restore_expected !== undefined && typeof item.restore_expected !== 'boolean') fail();
            const seen = item.outcomes_seen || [];
            if (!Array.isArray(seen) || seen.length > outcomes.length || seen.some(value => !outcomes.includes(value))) fail();
            return Object.freeze({ channel:item.channel, target:item.target, pause_outcome:item.pause_outcome,
              restore_outcome:item.restore_outcome, observed_state:item.observed_state, restore_expected:item.restore_expected === true, outcomes_seen:Object.freeze([...seen]) });
          }));
        };
        const projectedChannels = channels('channels'); const projectedUnknown = channels('unknown_channels');
        if (row.verified_restore) {
          const all = [...projectedChannels,...projectedUnknown];
          if (!all.length || !all.some(item=>item.restore_expected) || new Set(all.map(item => item.target)).size !== all.length) fail();
          const category = target => target.startsWith('camera.') ? 'camera_control' :
            Object.entries({'_audio_detection':'sound_detection','_audio':'sound_detection','_recordings':'recording','_snapshots':'snapshots','_detect':'detection','_motion':'motion','_enabled':'camera_control'}).find(([suffix])=>target.endsWith(suffix))?.[1] || 'unknown';
          for (const item of all) {
            if (item.channel !== category(item.target)) fail();
            if (!item.restore_expected) continue;
            if (item.target.startsWith('switch.')) {
              if (!item.target.startsWith(`switch.${row.camera_id}_`) || !['active','preexisting_off'].includes(item.restore_outcome) || item.observed_state !== (item.restore_outcome==='preexisting_off'?'off':'on')) fail();
            } else if (item.target !== `camera.${row.camera_id}` || item.restore_outcome !== 'active' || !['on','idle','streaming','recording'].includes(item.observed_state)) fail();
          }
        }
        return Object.freeze({ id:row.id,camera_id:row.camera_id,generation:row.generation,started_at:row.started_at,
          ended_at:row.ended_at,planned_ends_at:row.planned_ends_at,observed_at:row.observed_at,
          duration_seconds:row.duration_seconds,phase:row.phase,source:row.source,reason:row.reason,
          end_reason:row.end_reason,verified_restore:row.verified_restore,channels:projectedChannels,
          unknown_channels:projectedUnknown,evidence_scope:row.evidence_scope });
      });
      const durability = ['confirmed','loaded','not_written','not_loaded','save_failed','capture_failed'].includes(payload.durability) ? payload.durability : 'not_loaded';
      if (['corrupt','unsupported','unavailable'].includes(payload.status) && rows.length) fail();
      return { rows:Object.freeze(rows), info:Object.freeze({status:payload.status,durability}) };
    }
    _periodStrings() {
      return this._lang === 'pl' ? {
        expected:'Cel przywrócenia', yes:'Tak', no:'Nie', title:'Historia okresów', timeline:'Oś zdarzeń', data:'Dane', refresh:'Odczytaj historię', cancel:'Odrzuć odczyt',
        hint:'Zapisane przejścia integracji. Początek to intencja pauzy, nie dowód ciągłej ochrony fizycznej. Termin planowany nie jest końcem.',
        limitation:'Sterowanie kamerą nie dowodzi wyłączenia obrazu na żywo. Detekcja dźwięku nie dowodzi wyłączenia mikrofonu.',
        idle:'Historia wymaga jawnego odczytu.',loading:'Odczyt historii…',discarded:'Poprzedni wynik odrzucono. Odczytaj ponownie.',
        timeout:'Przekroczono termin odczytu. Odpowiedź będzie odrzucona; nowy odczyt po zakończeniu poprzedniego.',
        error:'Nie można potwierdzić historii. Spróbuj ponownie.',offline:'Połączenie jest niedostępne.',unknown:'Nieznany',open:'Brak zaobserwowanego końca',
        start:'Intencja rozpoczęcia',end:'Zaobserwowany koniec',planned:'Planowany termin',duration:'Czas między zdarzeniami (s)',
        reason:'Powód zakończenia',source:'Źródło',generation:'Generacja pauzy',restore:'Przywrócenie potwierdzone odczytem celów',
        noRestore:'Brak dowodu przywrócenia',previous:'Poprzednie',next:'Następne',page:'Strona',rows:'okresów',empty:'Brak zapisanych okresów w zakresie.',
        selected:'Szczegóły wybranego okresu',channels:'Wyniki kanałów',unknownChannels:'Nierozpoznane kanały',pause:'Pauza',resume:'Wznowienie',observed:'Odczyt celu',seen:'Zachowane wyniki',
        retained:'Do 200 okresów / 30 dni / 1 MiB; odczyt filtruje retencję bez zapisu.',zone:'Strefa wyświetlania',legacy:'Dane legacy: tylko ostatni rekord każdej kamery. Daty i pełna historia mogą być nieznane.',
        storage:'Trwałość zapisu',status:'Stan historii',ready:'Dostępna',corrupt:'Uszkodzony format — dane zachowano',unsupported:'Nieobsługiwana wersja — dane zachowano',unavailable:'Niedostępna',
        confirmed:'Potwierdzony zapis',loaded:'Odczytano ze Store',not_written:'Brak potwierdzonego zapisu',not_loaded:'Nie załadowano',save_failed:'Zapis nie powiódł się; pokazano ostatni trwały stan',capture_failed:'Nie udało się utrwalić projekcji historii',
        detection:'Detekcja',recording:'Nagrywanie',snapshots:'Zdjęcia',sound_detection:'Detekcja dźwięku',motion:'Ruch',camera_control:'Sterowanie kamerą',
      } : {
        expected:'Restore target', yes:'Yes', no:'No', title:'Period history',timeline:'Event timeline',data:'Data',refresh:'Read history',cancel:'Discard read',
        hint:'Recorded integration transitions. Start is pause intent, not proof of continuous physical protection. Planned deadline is not the end.',
        limitation:'Camera control does not prove live video is disabled. Sound detection does not prove the microphone is disabled.',
        idle:'History requires an explicit read.',loading:'Reading history…',discarded:'Previous result discarded. Read again.',
        timeout:'Read deadline exceeded. Its response will be discarded; a new read becomes available after settlement.',error:'History could not be confirmed. Try again.',offline:'Connection unavailable.',
        unknown:'Unknown',open:'No observed end',start:'Pause intent',end:'Observed end',planned:'Planned deadline',duration:'Time between events (s)',
        reason:'End reason',source:'Source',generation:'Pause generation',restore:'Restore verified by target readback',noRestore:'No verified restore',
        previous:'Previous',next:'Next',page:'Page',rows:'periods',empty:'No recorded periods in this range.',selected:'Selected period details',
        channels:'Channel outcomes',unknownChannels:'Unrecognized channels',pause:'Pause',resume:'Resume',observed:'Target readback',seen:'Retained outcomes',
        retained:'Up to 200 periods / 30 days / 1 MiB; reads filter retention without writes.',zone:'Display time zone',legacy:'Legacy data: only the latest record per camera. Dates and complete history may be unknown.',
        storage:'Storage durability',status:'History status',ready:'Available',corrupt:'Corrupt format — data preserved',unsupported:'Unsupported version — data preserved',unavailable:'Unavailable',
        confirmed:'Write confirmed',loaded:'Loaded from Store',not_written:'No confirmed write',not_loaded:'Not loaded',save_failed:'Save failed; last durable state shown',capture_failed:'History projection could not be saved',
        detection:'Detection',recording:'Recording',snapshots:'Snapshots',sound_detection:'Sound detection',motion:'Motion',camera_control:'Camera control',
      };
    }
    _periodTime(value) { return this._formatUi().pointLabel(value)||this._periodStrings().unknown; }
    _periodText(value) {
      const labels = {
        unknown:['Unknown','Nieznany'], manual:['Manual','Ręczne'], schedule:['Schedule','Harmonogram'],
        pausing:['Pausing','Wstrzymywanie'], resuming:['Resuming','Wznawianie'], partial:['Partial','Częściowo'], error:['Error','Błąd'],
        pending:['Pending','Oczekuje'], missing:['Not present','Brak kanału'], unavailable:['Unavailable','Niedostępny'],
        preexisting_off:['Already off before pause','Wyłączony przed pauzą'], paused:['Paused','Wstrzymany'], active:['Restored','Przywrócony'],
        service_failed:['Command failed','Błąd polecenia'], readback_failed:['Readback failed','Błąd potwierdzenia'], failed:['Failed','Niepowodzenie'],
        repaused:['Paused again','Ponownie wstrzymany'], re_pause_readback_failed:['Pause readback failed','Błąd potwierdzenia ponownej pauzy'],
        re_pause_cancelled:['Pause cancelled','Ponowna pauza anulowana'], re_pause_service_failed:['Pause command failed','Błąd polecenia ponownej pauzy'],
        on:['On','Włączony'], off:['Off','Wyłączony'], idle:['Idle','Gotowy'], streaming:['Streaming','Transmisja obrazu'], recording:['Recording','Nagrywanie'],
        pause_incomplete:['Pause incomplete','Pauza niepełna'], manual_override:['Manual intervention','Ręczna zmiana'], admin_request:['Administrator request','Żądanie administratora'],
        schedule_window_ended:['Schedule ended','Koniec harmonogramu'], manual_deadline_elapsed:['Duration elapsed','Upłynął wybrany czas'],
        restart_recovery:['Restart recovery','Odzyskiwanie po restarcie'], restart_during_pause:['Restart during pause','Restart podczas pauzy'],
        recovery_targets_missing:['Recovery targets missing','Brak celów odzyskiwania'], switch_unavailable:['Switch unavailable','Przełącznik niedostępny'],
        resume_failed:['Restore failed','Przywrócenie nieudane'], resume_cancelled:['Restore cancelled','Przywrócenie anulowane'],
        state_persistence_failed:['State save failed','Błąd zapisu stanu'], invalid_persisted_targets:['Invalid saved targets','Nieprawidłowe zapisane cele'],
        invalid_persisted_state:['Invalid saved state','Nieprawidłowy zapisany stan'], recovery_pending:['Recovery pending','Oczekiwanie na odzyskanie'],
      };
      return labels[value]?.[this._lang === 'pl' ? 1 : 0] || this._periodStrings().unknown;
    }
    _periodCameraLabel(cameraId) {
      const current = this._cameras.find(camera => camera.camera_id === cameraId);
      return typeof current?.name === 'string' && current.name ? current.name : cameraId.replace(/_/g, ' ');
    }
    _periodResult(row) {
      return row.verified_restore ? 'success' : row.end_reason === 'manual_override' ? 'unconfirmed' :
        row.phase === 'error' ? 'error' : row.phase === 'partial' ? 'partial' : row.ended_at ? 'unconfirmed' : 'not_checked';
    }
    _buildHistoryTab() {
      const t = this._periodStrings(); const ui = createUiV3({language:this._lang});
      const count = this._periods.length; const pages = Math.max(1,Math.ceil(count/50));
      this._periodPage = Math.min(this._periodPage,pages-1);
      const rows = this._periods.slice(this._periodPage*50,this._periodPage*50+50);
      const unavailable = !this._periodAuthority();
      const info = this._periodInfo; const zone = this._formatUi().timeZone;
      const end = row => row.ended_at ? this._periodTime(row.ended_at) : t.open;
      const selection = row => `<button type="button" class="period-select ${this._periodSelected===row.id?'selected':''}" data-period-select="${_esc(row.id)}" aria-pressed="${this._periodSelected===row.id}" title="${_esc(row.camera_id)}">${_esc(this._periodCameraLabel(row.camera_id))}</button>`;
      const timeline = `<ol class="period-timeline">${rows.map(row => `<li>${selection(row)}<div class="period-event"><span>${_esc(t.start)}</span><time datetime="${_esc(row.started_at||'')}">${_esc(this._periodTime(row.started_at))}</time><span>${_esc(t.end)}</span><span>${_esc(end(row))}</span></div>${ui.statusHtml(this._periodResult(row))}</li>`).join('')}</ol>`;
      const data = `<div class="period-table-wrap"><table class="period-table"><caption>${_esc(t.data)} · ${_esc(zone)} · UTC</caption><thead><tr><th>${_esc(this._t.cameras)}</th><th>${_esc(t.start)}</th><th>${_esc(t.end)}</th><th>${_esc(t.duration)}</th><th>${_esc(t.reason)}</th></tr></thead><tbody>${rows.map(row => `<tr><td data-label="${_esc(this._t.cameras)}">${selection(row)}</td><td data-label="${_esc(t.start)}">${_esc(this._periodTime(row.started_at))}</td><td data-label="${_esc(t.end)}">${_esc(end(row))}</td><td data-label="${_esc(t.duration)}">${_esc(row.duration_seconds ?? t.unknown)}</td><td data-label="${_esc(t.reason)}">${_esc(this._periodText(row.end_reason))} ${ui.statusHtml(this._periodResult(row))}</td></tr>`).join('')}</tbody></table></div>`;
      const selected = this._periods.find(row => row.id === this._periodSelected);
      const evidence = (items,heading) => items.length ? `<div class="period-evidence"><h4>${_esc(heading)}</h4>${items.map(item => `<div><strong>${_esc(t[item.channel]||t.unknown)}</strong><code>${_esc(item.target)}</code><dl><dt>${_esc(t.expected)}</dt><dd>${_esc(item.restore_expected?t.yes:t.no)}</dd><dt>${_esc(t.pause)}</dt><dd>${_esc(this._periodText(item.pause_outcome))}</dd><dt>${_esc(t.resume)}</dt><dd>${_esc(this._periodText(item.restore_outcome))}</dd><dt>${_esc(t.observed)}</dt><dd>${_esc(this._periodText(item.observed_state))}</dd><dt>${_esc(t.seen)}</dt><dd>${_esc(item.outcomes_seen.map(value=>this._periodText(value)).join(', ')||t.unknown)}</dd></dl></div>`).join('')}</div>` : '';
      const detail = selected ? `<section class="period-detail" aria-label="${_esc(t.selected)}"><h3>${_esc(t.selected)} · ${_esc(selected.camera_id)}</h3>${ui.statusHtml(this._periodResult(selected))}<p>${_esc(selected.verified_restore?t.restore:t.noRestore)}</p><dl>${[[t.start,this._periodTime(selected.started_at)],[t.end,end(selected)],[t.planned,this._periodTime(selected.planned_ends_at)],[t.duration,selected.duration_seconds??t.unknown],[t.reason,this._periodText(selected.end_reason)],[this._t.reason,this._periodText(selected.reason)],[t.source,this._periodText(selected.source)],[t.generation,selected.generation??t.unknown]].map(([key,value])=>`<dt>${_esc(key)}</dt><dd>${_esc(value)}</dd>`).join('')}</dl><p class="helper">UTC: ${_esc(selected.started_at||t.unknown)} → ${_esc(selected.ended_at||t.unknown)}</p>${evidence(selected.channels,t.channels)}${evidence(selected.unknown_channels,t.unknownChannels)}</section>` : '';
      return `<section class="history-panel section"><style>${ui.css}</style><div class="section-head"><h3>${_esc(t.title)}</h3></div><p class="helper">${_esc(t.hint)}</p><div class="period-toolbar"><label>${_esc(this._lang==='pl'?'Zakres czasu':'Time range')}<select data-period-range aria-label="${_esc(t.title)}"><option value="7" ${this._periodDays===7?'selected':''}>7 ${this._lang==='pl'?'dni':'days'}</option><option value="30" ${this._periodDays===30?'selected':''}>30 ${this._lang==='pl'?'dni':'days'}</option></select></label><button type="button" class="btn btn-primary" data-period-refresh ${unavailable||this._periodWire?'disabled':''}>${_esc(t.refresh)}</button>${this._periodWire?`<button type="button" class="btn btn-secondary" data-period-cancel>${_esc(t.cancel)}</button>`:''}</div><p class="helper" role="status">${_esc(unavailable?t.offline:this._periodState==='ready'?'':t[this._periodState]||t.idle)}</p>${info?`<p class="helper">${_esc(t.status)}: ${_esc(t[info.status]||info.status)} · ${_esc(t.storage)}: ${_esc(t[info.durability])}</p>${info.status==='legacy_latest'?`<p class="helper">${_esc(t.legacy)}</p>`:''}`:''}<p class="helper">${_esc(t.retained)} ${_esc(t.zone)}: ${_esc(zone)}. UTC.</p>${count?`<div class="period-toolbar" role="group" aria-label="${_esc(t.title)}">${[['timeline',t.timeline],['data',t.data]].map(([value,label])=>`<button type="button" class="btn btn-secondary" data-period-view="${value}" aria-pressed="${this._periodView===value}">${_esc(label)}</button>`).join('')}</div>${this._periodView==='data'?data:timeline}<nav class="period-pagination" aria-label="${_esc(t.page)}"><button type="button" class="btn btn-secondary" data-period-page="previous" ${this._periodPage===0?'disabled':''}>${_esc(t.previous)}</button><span>${_esc(t.page)} ${this._periodPage+1}/${pages} · ${count} ${_esc(t.rows)}</span><button type="button" class="btn btn-secondary" data-period-page="next" ${this._periodPage>=pages-1?'disabled':''}>${_esc(t.next)}</button></nav>${detail}`:info&&['ready','legacy_latest'].includes(info.status)?`<div class="empty">${_esc(t.empty)}</div>`:''}<p class="helper">${_esc(t.limitation)}</p></section>`;
    }
    _attachPeriodEvents() {
      const root = this.shadowRoot;
      root.querySelector('[data-period-refresh]')?.addEventListener('click',()=>this._refreshPeriods());
      root.querySelector('[data-period-cancel]')?.addEventListener('click',()=>{this._invalidatePeriods('discarded');this._updateUI();});
      root.querySelector('[data-period-range]')?.addEventListener('change',event=>this._setPeriodRange(event.target.value));
      root.querySelectorAll('[data-period-view]').forEach(button=>button.addEventListener('click',()=>{this._periodView=button.dataset.periodView;this._updateUI();}));
      root.querySelectorAll('[data-period-select]').forEach(button=>button.addEventListener('click',()=>{this._periodSelected=button.dataset.periodSelect;this._updateUI();}));
      root.querySelectorAll('[data-period-page]').forEach(button=>button.addEventListener('click',()=>{this._periodPage+=button.dataset.periodPage==='next'?1:-1;this._updateUI();}));
    }

    _buildInfoTab() { const t=this._t; return `<div class="section"><div class="section-head"><h3>${_esc(t.architecture)}</h3></div><p class="helper">${_esc(t.architectureText)}</p></div>`; }
    _actionExample() {
      const kind = this._actionKind || 'button_pause'; const resume = kind.includes('resume');
      const action = `ha_frigate_privacy.${resume ? 'resume_camera' : 'pause_camera'}`;
      const cameras = this._selectedCameraIds();
      const lines = [...(cameras?.length ? [`camera: ${JSON.stringify(cameras)}`] : []), ...(resume ? [] : [`stream_type: ${this._pauseStreamType}`, `duration_minutes: ${Math.max(1, Math.min(1440, Number(this._customMinutes) || 30))}`])];
      const data = lines.length ? `\n    data:\n${lines.map((line)=>'      '+line).join('\n')}` : '';
      if (kind.startsWith('button')) return `type: button\nname: Frigate Privacy ${resume?'Resume':'Pause'}\nicon: mdi:shield-lock-outline\ntap_action:\n  action: perform-action\n  perform_action: ${action}${lines.length ? `\n  data:\n${lines.map((line)=>'    '+line).join('\n')}` : ''}`;
      if (kind.startsWith('script')) return `alias: Frigate Privacy ${resume?'Resume':'Pause'}\nsequence:\n  - action: ${action}${data}\nmode: single`;
      if (kind === 'scene') return `# Helper: input_boolean.frigate_privacy\n# Set this helper on/off in your HA scene.\n# Trust this automation in Frigate Privacy options.\nalias: Frigate Privacy scene bridge\ntriggers:\n  - trigger: state\n    entity_id: input_boolean.frigate_privacy\n    to: ["on", "off"]\nactions:\n  - choose:\n      - conditions: "{{ trigger.to_state.state == 'on' }}"\n        sequence:\n          - action: ha_frigate_privacy.pause_camera${lines.length ? `\n            data:\n${lines.map((line)=>'              '+line).join('\n')}` : ''}\n    default:\n      - action: ha_frigate_privacy.resume_camera${cameras?.length ? `\n        data:\n          camera: ${JSON.stringify(cameras)}` : ''}\nmode: single`;
      return `# Add your physical-button or other trigger in the HA editor.\n# Add this automation to Frigate Privacy trusted actions.\n- action: ${action}${lines.length ? `\n  data:\n${lines.map((line)=>'    '+line).join('\n')}` : ''}`;
    }
    _buildActionsTab() {
      const t=this._t,kind=this._actionKind||'button_pause';
      return `${this._buildNotificationSetup()}<div class="section"><div class="section-head"><h3>${_esc(t.actions)}</h3></div><p>${_esc(t.actionHint)}</p><p class="helper" style="margin-top:12px">${_esc(t.trustHint)}</p><div class="action-links"><a href="/config/integrations/integration/ha_frigate_privacy">${_esc(this._lang==='pl'?'Ustaw zaufaną automatyzację':'Set up a trusted automation')}</a></div></div><div class="section"><label for="action-kind">${_esc(t.example)}</label><select id="action-kind" class="action-kind">${[['button_pause',t.buttonPause],['button_resume',t.buttonResume],['script_pause',t.scriptPause],['script_resume',t.scriptResume],['automation_pause',t.automationPause],['scene',t.sceneHelper]].map(([value,label])=>`<option value="${value}" ${kind===value?'selected':''}>${_esc(label)}</option>`).join('')}</select>${kind==='scene'?`<p class="helper">${_esc(t.sceneHint)}</p>`:''}<textarea class="action-example" aria-label="${_esc(t.example)}" readonly>${_esc(this._actionExample())}</textarea><button class="btn btn-secondary" data-action="copy-example">${_esc(t.copy)}</button><div class="action-links"><a href="/config/automation/dashboard">${_esc(t.automationPause)}</a><a href="/config/script/dashboard">${_esc(t.scriptPause)}</a><a href="/config/scene/dashboard">${_esc(t.sceneHelper)}</a></div></div>`;
    }
    _notificationStrings() {
      return this._lang==='pl'?{
        title:'Powiadomienia',off:'Wyłączone — nie wybrano odbiorcy',unknown:'Zapisane ustawienia niepotwierdzone. Odśwież je po powrocie z Konfiguruj.',unavailable:'Zapisany odbiorca jest obecnie niedostępny. Wybierz innego w ustawieniach.',destination:'Zapisany odbiorca',events:'Zdarzenia',none:'Żadne — powiadomienia o zdarzeniach nie będą wysyłane',labels:{errors:'Błędy i częściowa prywatność',paused:'Pauza',resumed:'Przywrócenie',scheduled:'Początek i koniec harmonogramu'},
        steps:['Otwórz ustawienia powiadomień. Na stronie integracji wybierz Konfiguruj.','W polu Odbiorca wybierz powiadomienia w Home Assistant albo dostępny kanał lub urządzenie. Jeśli telefonu nie ma na liście, najpierw skonfiguruj jego powiadomienia w Home Assistant.','Wybierz zdarzenia i zapisz formularz. Wróć tutaj i odśwież zapisane ustawienia.','Kliknij Wyślij test, aby sprawdzić zapisany kanał.'],path:'Ustawienia → Urządzenia i usługi → Frigate Privacy → Konfiguruj',setup:'Ustaw powiadomienia',refresh:'Odśwież zapisane ustawienia',test:'Wyślij test',sending:'Wysyłanie…',independent:'Powiadomienia nie wymagają dodawania zaufanych automatyzacji.',ha_accepted:'Home Assistant przyjął test. Sprawdź wybrany kanał. To nie potwierdza doręczenia na telefon.',error:'Nie udało się wysłać testu przez Home Assistant. Sprawdź kanał w ustawieniach i spróbuj ponownie.',no_channel:'Nie ma dostępnego zapisanego kanału. Wybierz odbiorcę i zapisz ustawienia.',unconfirmed:'Wynik testu niepotwierdzony. Nie wysyłamy go ponownie automatycznie.'
      }:{
        title:'Notifications',off:'Off — no destination selected',unknown:'Saved settings unconfirmed. Refresh them after returning from Configure.',unavailable:'The saved destination is currently unavailable. Choose another in settings.',destination:'Saved destination',events:'Events',none:'None — event notifications will not be sent',labels:{errors:'Errors and partial privacy',paused:'Pause',resumed:'Restoration',scheduled:'Scheduled start and restoration'},
        steps:['Open notification settings. On the integration page, choose Configure.','Under Destination, choose notifications in Home Assistant or an available channel or device. If your phone is missing, set up its notifications in Home Assistant first.','Choose events and save the form. Return here and refresh the saved settings.','Choose Send test to check the saved destination.'],path:'Settings → Devices & services → Frigate Privacy → Configure',setup:'Set up notifications',refresh:'Refresh saved settings',test:'Send test',sending:'Sending…',independent:'Notifications do not require trusted automations.',ha_accepted:'Home Assistant accepted the test. Check the selected destination. This does not confirm delivery to a phone.',error:'Home Assistant could not send the test. Check the destination in settings and try again.',no_channel:'No saved destination is available. Choose a destination and save the settings.',unconfirmed:'Test result unconfirmed. We do not send it again automatically.'
      };
    }
    _buildNotificationSetup() {
      const t=this._notificationStrings(),n=this._notifications;
      const labels=n?Object.entries(t.labels).filter(([key])=>n.events[key]===true).map(([,label])=>label):[];
      const status=!n?t.unknown:!n.destination?t.off:!n.available?t.unavailable:`${t.destination}: ${n.label}`;
      const result=this._notificationResult&&Object.hasOwn(t,this._notificationResult)?t[this._notificationResult]:'';
      return `<section class="section" data-notification-setup><div class="section-head"><h3>${_esc(t.title)}</h3></div><p role="status" data-notification-saved>${_esc(status)}</p>${n?.destination?`<p>${_esc(t.events)}: ${_esc(labels.join(', ')||t.none)}</p>`:''}<ol class="notification-steps">${t.steps.map(step=>`<li>${_esc(step)}</li>`).join('')}</ol><p class="helper">${_esc(t.path)}</p><div class="notification-actions"><a class="btn btn-primary" href="/config/integrations/integration/ha_frigate_privacy">${_esc(t.setup)}</a><button type="button" class="btn btn-secondary" data-notification-refresh ${this._connectPromise?'disabled':''}>${_esc(t.refresh)}</button><button type="button" class="btn btn-secondary" data-notification-test ${!n?.destination||!n.available||this._notificationWire?'disabled':''}>${_esc(this._notificationWire?t.sending:t.test)}</button></div><p class="helper">${_esc(t.independent)}</p><p role="status" data-notification-result>${_esc(result)}</p></section>`;
    }
    async _testNotification() {
      if(this._notificationWire||!this._periodAuthority()||!this._notifications?.destination||!this._notifications.available)return;
      const epoch=this._notificationEpoch,hass=this._hass,connection=this._connection,user=this._userId,instance=this._instanceId;
      const current=()=>epoch===this._notificationEpoch&&connection===this._connection&&user===this._userId&&instance===this._instanceId&&this._hass?.user?.id===user&&this._hass?.connection===connection&&(this._hass?.config?.instance_id||null)===instance&&this._periodAuthority();
      let expired=false;this._notificationResult=null;
      const wire=Promise.resolve().then(()=>{if(!current())throw new Error('context_changed');return hass.callWS({type:'ha_frigate_privacy/test_notification'});});
      this._notificationWire=wire;
      this._notificationTimer=setTimeout(()=>{expired=true;if(current()){this._notificationResult='unconfirmed';this._updateUI();}},15000);
      this._updateUI();
      try {
        const result=await wire;
        if(current()&&!expired)this._notificationResult=['ha_accepted','error','no_channel'].includes(result?.status)?result.status:'unconfirmed';
      } catch(error) {
        if(current()){
          if(error?.code==='unauthorized'){this._denyAccess();return;}
          this._notificationResult='unconfirmed';
        }
      } finally {
        if(this._notificationWire===wire)this._notificationWire=null;
        if(epoch===this._notificationEpoch){if(this._notificationTimer)clearTimeout(this._notificationTimer);this._notificationTimer=null;}
        if(current())this._updateUI();
      }
    }
    _buildHTML() { const t=this._t;const gate=this._buildGate();const summary=this._phaseSummary();const title=this._config.title||'Frigate Privacy';const main=gate||`<select class="tab-picker" data-tab-picker aria-label="${_esc(this._lang==='pl'?'Sekcje karty':'Card sections')}" hidden>${[['control',t.control],['schedule',t.schedule],['state',t.state],['history',this._periodStrings().title],['actions',t.actions],['info',t.info]].map(([id,label])=>`<option value="${id}" ${this._activeTab===id?'selected':''}>${_esc(label)}</option>`).join('')}</select><div class="tabs" role="tablist" aria-label="${_esc(this._lang==='pl'?'Sekcje karty':'Card sections')}">${[['control',t.control],['schedule',t.schedule],['state',t.state],['history',this._periodStrings().title],['actions',t.actions],['info',t.info]].map(([id,label])=>`<button class="tab-btn ${this._activeTab===id?'active':''}" data-tab="${id}" role="tab" aria-selected="${this._activeTab===id}">${_esc(label)}</button>`).join('')}</div>${this._activeTab==='control'?this._buildControlTab():this._activeTab==='schedule'?this._buildScheduleTab():this._activeTab==='state'?this._buildStateTab():this._activeTab==='history'?this._buildHistoryTab():this._activeTab==='actions'?this._buildActionsTab():this._buildInfoTab()}`;return `<style>${CSS}${createUiV3({language:this._lang}).css}</style><div class="card"><div class="header"><div class="brand"><div class="brand-mark"><ha-icon icon="mdi:shield-lock-outline"></ha-icon></div><div><h2>${_esc(title)}</h2><p class="subtitle">${_esc(t.subtitle)}</p></div></div>${summary.camera?`<button type="button" class="status-pill ${_esc(summary.phase)}" data-camera-summary="${_esc(summary.camera)}"><span class="status-dot" aria-hidden="true"></span>${_esc(summary.label)}</button>`:`<div class="status-pill ${_esc(summary.phase)}"><span class="status-dot"></span>${_esc(this._integrationChecked?summary.label:t.connecting)}</div>`}</div><div class="body">${this._buildIntroBanner()}${this._buildMutationResult()}${this._error&&!this._mutationOutcome?`<div class="notice error" style="margin-bottom:16px"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><div><h3>${_esc(t.failed)}</h3><p>${_esc(this._error)}</p></div></div>`:''}${main}${this._buildDonateFooter()}</div><div class="toast"></div></div>`; }
    _syncNavigation() {
      if (!this._navigationObserver && this.isConnected && typeof ResizeObserver === 'function') {
        this._navigationObserver = new ResizeObserver(() => this._syncNavigation()); this._navigationObserver.observe(this);
      }
      const root = this.shadowRoot, group = root.querySelector('.tabs'), picker = root.querySelector('[data-tab-picker]');
      if (!group || !picker) return;
      const width = this.getBoundingClientRect().width, compact = width > 0 && width < 280;
      const active = root.activeElement;
      picker.value = this._activeTab;
      if (compact) {
        picker.hidden = false;
        if (group.contains(active)) picker.focus({preventScroll:true});
        group.hidden = true;
      } else {
        group.hidden = false;
        if (active === picker) group.querySelector('[aria-selected="true"]')?.focus({preventScroll:true});
        picker.hidden = true;
      }
      if (this._pendingControlFocus?.anchor === active && root.activeElement !== active) this._pendingControlFocus.anchor = root.activeElement;
    }
    _focusControl(element) {
      if (element?.matches('[data-tab]') && element.closest('.tabs')?.hidden) element = this.shadowRoot.querySelector('[data-tab-picker]');
      if (element?.matches('[data-tab-picker]') && element.hidden) element = this.shadowRoot.querySelector('[data-tab][aria-selected="true"]');
      if (!element || element.disabled || element.closest('[hidden]')) return null;
      element.focus({preventScroll:true}); return element;
    }
    _updateUI() {
      if (this._previewCamera && !this._previewAllowed(this._previewCamera)) this._closePreview();
      const html = this._buildHTML();
      if (html === this._lastHtml) { this._tickCountdowns(); this._syncPreview(); this._syncNavigation(); if (!this._busy) this._pendingControlFocus = null; return; }
      const active = this.shadowRoot.activeElement;
      const snapshot = this._pendingControlFocus && active === this._pendingControlFocus.anchor ? this._pendingControlFocus.snapshot : active ? {
        tag:active.tagName, id:active.id, classes:active.className,
        keys:[...active.attributes].filter(attr => attr.name.startsWith('data-')).map(attr => [attr.name,attr.value]),
        selection:['INPUT','TEXTAREA'].includes(active.tagName) ? {value:active.tagName === 'INPUT' ? active.value : null,start:active.selectionStart,end:active.selectionEnd,direction:active.selectionDirection} : null,
      } : null;
      this._pendingControlFocus = null;
      this._lastHtml = html; this.shadowRoot.innerHTML = html; this._attachEvents(); this._syncNavigation(); this._tickCountdowns(); this._syncPreview();
      if (!snapshot) return;
      const next = [...this.shadowRoot.querySelectorAll('button,input,select,textarea,[tabindex]')].find(element => element.tagName === snapshot.tag && (snapshot.id ? element.id === snapshot.id : snapshot.keys.length ? snapshot.keys.every(([name,value]) => element.getAttribute(name) === value) : element.className === snapshot.classes));
      const restored = this._focusControl(next);
      if (restored) {
        if (snapshot.selection?.value != null) restored.value = snapshot.selection.value;
        if (snapshot.selection?.start != null) restored.setSelectionRange(snapshot.selection.start,snapshot.selection.end,snapshot.selection.direction);
        return;
      }
      const fallback = this._focusControl(this.shadowRoot.querySelector(snapshot.keys.some(([name]) => name === 'data-period-page') ? '[data-period-select]' : '[data-tab][aria-selected="true"]'));
      // A visible anchor retains keyboard intent through disabled controls. User focus moves cancel it.
      if (this._busy && fallback) this._pendingControlFocus = {snapshot,anchor:fallback};
    }

    _attachEvents() {
      this._attachPeriodEvents();
      this.shadowRoot.querySelector('[data-camera-summary]')?.addEventListener('click',event=>{
        const id=event.currentTarget.dataset.cameraSummary;this.setActiveTab('control');
        const camera=[...this.shadowRoot.querySelectorAll('[data-camera]')].find(node=>node.dataset.camera===id);
        camera?.scrollIntoView?.({block:'nearest',behavior:'smooth'});this._focusControl(camera);
      });
      this.shadowRoot.querySelector('[data-notification-refresh]')?.addEventListener('click',()=>{if(!this._connectPromise)this._connectIntegration();});
      this.shadowRoot.querySelector('[data-notification-test]')?.addEventListener('click',()=>this._testNotification());
      const root=this.shadowRoot;root.querySelector('[data-action="dismiss-intro"]')?.addEventListener('click',()=>this._dismissIntro());root.querySelector('[data-action="dismiss-support"]')?.addEventListener('click',()=>this._dismissSupport());root.querySelector('[data-action="retry"]')?.addEventListener('click',()=>this._connectIntegration());
      root.querySelector('.action-kind')?.addEventListener('change',(event)=>{this._actionKind=event.target.value;this._updateUI();});
      root.querySelector('[data-action="copy-example"]')?.addEventListener('click',async()=>{const field=root.querySelector('.action-example');try{await navigator.clipboard.writeText(field.value);this._showToast(this._t.copied,'success');}catch(_){field.focus();field.select();}});
      root.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>this.setActiveTab(button.dataset.tab)));
      root.querySelector('[data-tab-picker]')?.addEventListener('change',event=>{this.setActiveTab(event.target.value);this._focusControl(root.querySelector('[data-tab-picker]'));});
      root.querySelectorAll('[data-camera]').forEach((card)=>{const toggle=()=>{const id=card.dataset.camera;if(id==='__all__')this._selectedCameras.clear();else if(this._selectedCameras.has(id))this._selectedCameras.delete(id);else this._selectedCameras.add(id);this._updateUI();};card.addEventListener('click',toggle);card.addEventListener('keydown',(event)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();toggle();}});});
      root.querySelectorAll('[data-preview-camera]').forEach(button=>button.addEventListener('click',()=>this._togglePreview(button.dataset.previewCamera)));
      root.querySelectorAll('[data-scope]').forEach((button)=>button.addEventListener('click',()=>{this._pauseStreamType=button.dataset.scope;haToolsPersistence.save('ha-frigate-privacy-pause-stream-type',this._pauseStreamType);this._updateUI();}));
      root.querySelector('.input-minutes')?.addEventListener('change',(event)=>{this._customMinutes=Math.max(1,Math.min(1440,Number.parseInt(event.target.value,10)||30));this._updateUI();});
      root.querySelector('[data-action="pause-custom"]')?.addEventListener('click',()=>this._pause());root.querySelector('[data-action="resume"]')?.addEventListener('click',()=>this._resume());
      root.querySelectorAll('[data-retry-camera]').forEach((button)=>button.addEventListener('click',()=>this._retryResume(button.dataset.retryCamera)));
      root.querySelectorAll('[data-schedule-edit]').forEach((button)=>button.addEventListener('click',()=>this._editSchedule(Number(button.dataset.scheduleEdit))));root.querySelectorAll('[data-schedule-delete]').forEach((button)=>button.addEventListener('click',()=>this._deleteSchedule(Number(button.dataset.scheduleDelete))));root.querySelectorAll('[data-schedule-toggle]').forEach((button)=>button.addEventListener('click',()=>this._toggleSchedule(Number(button.dataset.scheduleToggle))));
      root.querySelector('.input-label')?.addEventListener('input',(event)=>{this._scheduleForm.label=event.target.value;});root.querySelector('.input-start')?.addEventListener('change',(event)=>{const [hour,minute]=event.target.value.split(':').map(Number);this._scheduleForm.startHour=hour;this._scheduleForm.startMin=minute;});root.querySelector('.input-end')?.addEventListener('change',(event)=>{const [hour,minute]=event.target.value.split(':').map(Number);this._scheduleForm.endHour=hour;this._scheduleForm.endMin=minute;});
      root.querySelectorAll('[data-day]').forEach((button)=>button.addEventListener('click',()=>{const day=Number(button.dataset.day);const days=this._scheduleForm.days;this._scheduleForm.days=days.includes(day)?days.filter((item)=>item!==day):[...days,day].sort();this._updateUI();}));root.querySelector('[data-action="save-schedule"]')?.addEventListener('click',()=>this._saveScheduleFromForm());root.querySelector('[data-action="cancel-edit"]')?.addEventListener('click',()=>{this._editingScheduleIdx=null;this._scheduleForm=this._emptySchedule();this._updateUI();});
    }
    _showToast(message,kind) { const toast=this.shadowRoot.querySelector('.toast');if(!toast)return;toast.textContent=String(message||'');toast.className=`toast show ${kind==='error'?'error':''}`;if(this._toastTimer)clearTimeout(this._toastTimer);this._toastTimer=setTimeout(()=>{if(toast.isConnected)toast.className='toast';},2600); }
    setActiveTab(tabId) { if(['control','schedule','state','history','actions','info'].includes(tabId)){if(tabId!=='control')this._closePreview();this._activeTab=tabId;this._updateUI();} }
  }

  if (!customElements.get('ha-frigate-privacy')) customElements.define('ha-frigate-privacy', HaFrigatePrivacy);
  class HaFrigatePrivacyEditor extends HTMLElement {
    constructor(){super();this.attachShadow({mode:'open'});this._config={};}
    set hass(hass){this._hass=hass;this._render();}
    setConfig(config){this._config={...config};this._render();}
    connectedCallback(){this._render();}
    _render(){
      let input=this.shadowRoot.querySelector('#cf_title');
      if(!input){
        this.shadowRoot.innerHTML=`<style>:host{display:block;padding:16px;font-size:15px;line-height:1.5}label{display:block;margin-bottom:7px;font-size:14px;color:var(--secondary-text-color)}input{width:100%;box-sizing:border-box;min-height:44px;padding:10px 12px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);color:var(--primary-text-color)}input:focus-visible{outline:3px solid var(--primary-color,#3b82f6);outline-offset:2px}</style><label for="cf_title"></label><input id="cf_title" maxlength="80">`;
        input=this.shadowRoot.querySelector('#cf_title');
        input.addEventListener('input',event=>{this._config={...this._config,title:event.target.value};this.dispatchEvent(new CustomEvent('config-changed',{detail:{config:this._config},bubbles:true,composed:true}));});
      }
      this.shadowRoot.querySelector('label').textContent=String(this._hass?.language||navigator.language||'').startsWith('pl')?'Tytuł':'Title';
      const value=String(this._config.title??'Frigate Privacy');if(input.value!==value)input.value=value;
    }
  }
  if (!customElements.get('ha-frigate-privacy-editor')) customElements.define('ha-frigate-privacy-editor', HaFrigatePrivacyEditor);
})();

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card?.type === 'ha-frigate-privacy')) window.customCards.push({ type: 'ha-frigate-privacy', name: 'Frigate Privacy', description: 'Admin-only, integration-owned Frigate camera privacy controls', preview: false });
