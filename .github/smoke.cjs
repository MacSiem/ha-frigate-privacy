// Runtime render smoke (jsdom) — instantiates this repo's card(s) with a mock hass
// and fails if a card throws or renders nothing. Catches runtime errors that
// `node --check` cannot (e.g. a render() calling an undefined method).
const { JSDOM } = require('jsdom');
const fs = require('fs');
const path = require('path');
const ROOT = process.cwd();

function listCardFiles() {
  const out = [];
  for (const f of fs.readdirSync(ROOT)) {
    if (f.endsWith('.js') && !/editor|\.min\./.test(f)) out.push(path.join(ROOT, f));
  }
  const cc = path.join(ROOT, 'custom_components');
  if (fs.existsSync(cc)) for (const d of fs.readdirSync(cc)) {
    const www = path.join(cc, d, 'www');
    if (fs.existsSync(www)) for (const f of fs.readdirSync(www)) {
      if (f.endsWith('.js') && !/editor|\.min\./.test(f)) out.push(path.join(www, f));
    }
  }
  return out;
}
function tagsIn(code) {
  return [...code.matchAll(/customElements\.define\(\s*['"]([a-z0-9-]+)['"]/g)]
    .map(m => m[1]).filter(t => !/editor$/.test(t));
}
function mockHass() {
  return {
    states: {}, themes: { darkMode: false, themes: {} }, language: 'en',
    locale: { language: 'en', number_format: 'language', time_format: '24' },
    user: { id: 'u', name: 'Demo', is_admin: true, is_owner: true },
    config: { unit_system: { temperature: 'C' }, version: '2025.6.0' },
    callApi: () => Promise.resolve({}), callService: () => Promise.resolve({}),
    callWS: () => Promise.resolve([]), sendWS: () => Promise.resolve([]),
    formatEntityState: (s) => (s && s.state != null) ? String(s.state) : '',
    formatEntityAttributeValue: () => '',
    connection: {
      subscribeEvents: () => Promise.resolve(() => {}),
      subscribeMessage: () => Promise.resolve(() => {}),
      sendMessagePromise: () => Promise.resolve([]), socket: { readyState: 1 }
    }
  };
}
function stub(window) {
  try { Object.defineProperty(window.navigator, 'language', { configurable: true, get: () => 'en-US' }); } catch (e) {}
  window.requestAnimationFrame = (cb) => setTimeout(() => { try { cb(Date.now()); } catch (e) {} }, 0);
  window.cancelAnimationFrame = () => {};
  window.matchMedia = window.matchMedia || (() => ({ matches: false, media: '', onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent() { return false; } }));
  class RO { observe() {} unobserve() {} disconnect() {} }
  window.ResizeObserver = window.ResizeObserver || RO;
  window.IntersectionObserver = window.IntersectionObserver || RO;
  const store = () => { let m = {}; return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: k => { delete m[k]; }, clear: () => { m = {}; }, key: () => null, get length() { return Object.keys(m).length; } }; };
  try { Object.defineProperty(window, 'localStorage', { configurable: true, value: store() }); } catch (e) {}
  try { Object.defineProperty(window, 'sessionStorage', { configurable: true, value: store() }); } catch (e) {}
}
const delay = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  const files = listCardFiles();
  const targets = [];
  for (const f of files) {
    const code = fs.readFileSync(f, 'utf8');
    for (const t of tagsIn(code)) targets.push({ file: f, tag: t });
  }
  if (!targets.length) { console.log('smoke: no custom elements found — skipping'); process.exit(0); }
  let pass = 0; const fail = [];
  for (const t of targets) {
    let problem = null;
    try {
      const dom = new JSDOM('<!DOCTYPE html><html><head></head><body></body></html>', { runScripts: 'dangerously', pretendToBeVisual: true, url: 'http://localhost/' });
      const { window } = dom;
      stub(window);
      const NativeMutationObserver = window.MutationObserver;
      let documentWideObservers = 0;
      window.MutationObserver = class extends NativeMutationObserver {
        observe(target, options) {
          if (target === window.document.body && options && options.subtree) documentWideObservers++;
          return super.observe(target, options);
        }
      };
      class ForeignCard extends window.HTMLElement {
        constructor() {
          super();
          this.attachShadow({ mode: 'open' });
          this.shadowRoot.innerHTML = '<div data-foreign-marker="true">foreign card</div>';
        }
      }
      window.customElements.define('ha-yaml-checker', ForeignCard);
      const foreign = window.document.createElement('ha-yaml-checker');
      window.document.body.appendChild(foreign);
      const foreignHtml = foreign.shadowRoot.innerHTML;
      window._haToolsEsc = (s) => typeof s === 'string'
        ? s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
        : (s == null ? '' : s);
      let asyncErr = null;
      window.addEventListener('error', e => { asyncErr = asyncErr || (e.error && e.error.message) || e.message; });
      window.onerror = (m) => { asyncErr = asyncErr || m; };
      window.eval(fs.readFileSync(t.file, 'utf8'));
      const el = window.document.createElement(t.tag);
      if (typeof el.setConfig === 'function') el.setConfig({ type: 'custom:' + t.tag });
      el.hass = mockHass();
      window.document.body.appendChild(el);
      el.hass = mockHass();
      await delay(350);
      const len = el.shadowRoot ? el.shadowRoot.innerHTML.length : 0;
      if (!el.shadowRoot) problem = 'no shadowRoot';
      else if (len < 50) problem = 'empty render (len=' + len + ')';
      else if (asyncErr) problem = 'async error: ' + asyncErr;
      else if (foreign.shadowRoot.innerHTML !== foreignHtml) problem = 'foreign HA Tools card was mutated';
      else if (documentWideObservers !== 0) problem = 'document-wide MutationObserver was registered';
      else {
        el._cameras = [{
          entity_id: ['camera.safe', '\"><img data-hostile-entity src=x onerror=alert(1)>'],
          name: ['Kitchen', '</span><img data-hostile-name src=x onerror=alert(1)>']
        }];
        el._lastHtml = '';
        if (typeof el._updateUI === 'function') el._updateUI();
        await delay(20);
        if (el.shadowRoot.querySelector('[data-hostile-entity], [data-hostile-name]')) problem = 'non-string camera data bypassed HTML escaping';
      }
      if (!problem && el.shadowRoot.querySelectorAll('.intro-banner[data-intro="ha-frigate-privacy"]').length !== 1) problem = 'local first-run intro missing or duplicated';
      else if (!problem && el.shadowRoot.querySelectorAll('.donate-section').length !== 1) problem = 'local support footer missing or duplicated';
      else if (!problem) {
        const dismiss = el.shadowRoot.querySelector('.intro-banner[data-intro="ha-frigate-privacy"] .intro-dismiss');
        if (!dismiss) problem = 'local intro dismiss control missing';
        else {
          dismiss.click();
          await delay(20);
          if (window.localStorage.getItem('ha-intro-dismissed-ha-frigate-privacy') !== '1') problem = 'intro dismissal was not persisted';
          else if (el.shadowRoot.querySelector('.intro-banner[data-intro="ha-frigate-privacy"]')) problem = 'dismissed intro remained visible';
          else {
            el._lastHtml = '';
            if (typeof el._updateUI === 'function') el._updateUI();
            await delay(20);
            if (el.shadowRoot.querySelector('.intro-banner[data-intro="ha-frigate-privacy"]')) problem = 'dismissed intro returned after rerender';
            else if (el.shadowRoot.querySelectorAll('.donate-section').length !== 1) problem = 'support footer did not survive rerender';
          }
        }
      }
      window.close();
    } catch (e) { problem = (e && e.message) ? e.message : String(e); }
    if (problem) fail.push(`${t.tag}  (${path.basename(t.file)})  -> ${problem}`); else pass++;
  }
  console.log(`smoke: ${targets.length} element(s) | PASS ${pass} | FAIL ${fail.length}`);
  fail.forEach(f => console.log('  FAIL ' + f));
  process.exit(fail.length ? 1 : 0);
})();
