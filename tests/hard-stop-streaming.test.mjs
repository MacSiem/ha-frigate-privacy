import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const cardSource = readFileSync(new URL('../ha-frigate-privacy.js', import.meta.url), 'utf8');
const controlSource = readFileSync(
  new URL('../custom_components/ha_frigate_privacy/control.py', import.meta.url),
  'utf8',
);

assert.match(
  controlSource,
  /"camera",\s*"turn_off",\s*\{"entity_id": cam_entity\}/s,
  'the integration backend must hard-stop the selected camera stream in all-stream mode',
);
assert.match(
  controlSource,
  /stream_type == "all"/,
  'hard camera stop must be limited to the all-stream privacy scope',
);
assert.match(
  controlSource,
  /expected_raw = paused\.get\("switches"\) or \[\][\s\S]*expected = list\(expected_raw\)/,
  'resume must use only the exact switches successfully changed by the pause',
);
assert.match(
  controlSource,
  /_persisted_targets_are_valid\([\s\S]*expected_raw/,
  'persisted exact targets must pass the Frigate allowlist before resume',
);

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  url: 'http://localhost/',
});
const { window } = dom;
window.requestAnimationFrame = (callback) => window.setTimeout(callback, 0);
window.cancelAnimationFrame = (handle) => window.clearTimeout(handle);
window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
window.eval(cardSource);

const calls = [];
const state = {
  cameras: [{ camera_id: 'front', entity_id: 'camera.front', name: 'Front' }],
  schedules: [],
  paused: {},
};
const card = window.document.createElement('ha-frigate-privacy');
card.setConfig({ type: 'custom:ha-frigate-privacy' });
card.hass = {
  states: {},
  themes: { darkMode: false },
  language: 'en',
  user: { id: 'owner', name: 'Owner', is_admin: true },
  callWS: async (message) => {
    calls.push(message);
    if (message.type.endsWith('/get_state')) return state;
    return { state };
  },
};
window.document.body.appendChild(card);
await new Promise((resolve) => setTimeout(resolve, 30));

card.shadowRoot.querySelector('[data-action="pause-custom"]')?.click();
await new Promise((resolve) => setTimeout(resolve, 30));

const pause = calls.find((message) => message.type === 'ha_frigate_privacy/pause_camera');
assert.ok(pause, 'the pause button must call the integration pause command');
assert.equal(pause.stream_type, 'all');
assert.equal(pause.duration_minutes, 30);
assert.ok(
  calls.every((message) => String(message.type).startsWith('ha_frigate_privacy/')),
  'the card must never leave the integration namespace',
);

dom.window.close();
console.log('integration-owned hard-stop assertions passed');
