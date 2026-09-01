import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const paths = [
  new URL('../ha-frigate-privacy.js', import.meta.url),
  new URL('../custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js', import.meta.url),
];
const [source, shipped] = paths.map((path) => readFileSync(path, 'utf8'));

assert.equal(shipped, source, 'root and shipped cards must stay byte-identical');

const forbidden = [
  ['browser token access', /access_token|accessToken|Bearer\s/i],
  ['frontend fetch', /\bfetch\s*\(/],
  ['configuration REST', /\/api\/config/],
  ['direct HA service call', /\.callService\s*\(/],
  ['helper creation', /timer\/create|input_text\/create/],
  ['retired panel route', /ha-tools-panel/],
  ['direct stream mutator', /_setCameraStreams\s*\(/],
  ['legacy helper bootstrap', /_ensureHAHelpers\s*\(/],
  ['legacy schedule automation', /_syncScheduleToHA\s*\(/],
  ['legacy local mode', /legacy localStorage mode|Browser legacy mode|local compatibility mode/i],
];

for (const [label, pattern] of forbidden) {
  assert.doesNotMatch(source, pattern, `${label} must not remain in the card`);
}

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost/',
});
const { window } = dom;
window.requestAnimationFrame = (callback) => window.setTimeout(callback, 0);
window.cancelAnimationFrame = (handle) => window.clearTimeout(handle);
window.matchMedia = () => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
});
window.eval(source);

const calls = [];
const card = window.document.createElement('ha-frigate-privacy');
card.setConfig({ type: 'custom:ha-frigate-privacy' });
card.hass = {
  states: {
    'camera.front': { state: 'streaming', attributes: { friendly_name: 'Front' } },
    'switch.front_detect': { state: 'on', attributes: {} },
    'switch.front_recordings': { state: 'on', attributes: {} },
  },
  services: {},
  themes: { darkMode: false },
  language: 'en',
  user: { id: 'member', name: 'Member', is_admin: false },
  callWS: async (message) => {
    calls.push(message);
    throw Object.assign(new Error('Unauthorized'), { code: 'unauthorized' });
  },
};
window.document.body.appendChild(card);
await new Promise((resolve) => setTimeout(resolve, 80));

const html = card.shadowRoot?.textContent || '';
assert.match(html, /admin|permission|required/i, 'non-admin state must explain the permission boundary');
assert.equal(
  card.shadowRoot?.querySelector('[data-action="pause-custom"]'),
  null,
  'non-admin users must not receive a pause control',
);
assert.equal(
  card.shadowRoot?.querySelector('[data-action="save-schedule"]'),
  null,
  'non-admin users must not receive a schedule mutation control',
);
assert.ok(
  calls.every((call) => String(call?.type || '').startsWith('ha_frigate_privacy/')),
  'every card request must stay inside the integration WebSocket namespace',
);

dom.window.close();
console.log('forbidden legacy and permission-boundary assertions passed');
