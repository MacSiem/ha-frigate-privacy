import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const source = readFileSync(new URL('../ha-frigate-privacy.js', import.meta.url), 'utf8');

function createCard(initialState, mutationResult = null) {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'http://localhost/',
  });
  const { window } = dom;
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  window.eval(source);
  const card = window.document.createElement('ha-frigate-privacy');
  card.setConfig({ type: 'custom:ha-frigate-privacy' });
  card.hass = {
    states: {},
    themes: { darkMode: false },
    language: 'en',
    user: { id: 'owner', is_admin: true },
    callWS: async (message) => {
      if (message.type.endsWith('/get_state')) return initialState;
      return mutationResult || { ok: true, phase: 'paused', state: initialState };
    },
  };
  window.document.body.appendChild(card);
  return { dom, card };
}

const initial = {
  cameras: [{ camera_id: 'front', entity_id: 'camera.front', name: 'Front' }],
  schedules: [],
  paused: {},
};

{
  const switchOnly = {
    ...initial,
    cameras: [
      { camera_id: 'front', entity_id: null, name: 'Front' },
      { camera_id: 'back', entity_id: null, name: 'Back' },
    ],
  };
  const { dom, card } = createCard(switchOnly);
  await new Promise((resolve) => setTimeout(resolve, 30));
  const calls = [];
  card._runMutation = async (command, payload) => { calls.push({ command, payload }); return true; };
  card.shadowRoot.querySelector('[data-camera="front"]')?.click();
  await card._pause();

  assert.deepEqual(Array.from(card._selectedCameraIds()), ['front']);
  assert.deepEqual(Array.from(calls[0].payload.cameras), ['front']);
  dom.window.close();
}

{
  const partial = {
    ok: false,
    phase: 'partial',
    state: {
      ...initial,
      paused: { front: { camera_id: 'front', phase: 'partial', active: true } },
    },
  };
  const { dom, card } = createCard(initial, partial);
  await new Promise((resolve) => setTimeout(resolve, 30));
  const toasts = [];
  card._showToast = (message, kind) => toasts.push({ message, kind });
  card.shadowRoot.querySelector('[data-action="pause-custom"]')?.click();
  await new Promise((resolve) => setTimeout(resolve, 30));

  assert.equal(card._error, 'partial');
  assert.equal(toasts.at(-1)?.kind, 'error');
  assert.equal(card._paused.front.phase, 'partial');
  dom.window.close();
}

{
  const { dom, card } = createCard(initial);
  await new Promise((resolve) => setTimeout(resolve, 30));
  card._editingScheduleIdx = 0;
  card._scheduleForm = {
    enabled: true,
    days: [7],
    startHour: 21,
    startMin: 15,
    endHour: 22,
    endMin: 45,
    repeat: true,
    label: 'KEEP',
  };
  card._runMutation = async () => false;
  await card._saveScheduleFromForm();

  assert.equal(card._editingScheduleIdx, 0);
  assert.equal(card._scheduleForm.label, 'KEEP');
  assert.deepEqual(Array.from(card._scheduleForm.days), [7]);
  dom.window.close();
}

{
  const { dom, card } = createCard(initial);
  await new Promise((resolve) => setTimeout(resolve, 30));
  card._lang = 'en';
  assert.match(card._safeError({ code: 'replay_saturated' }), /blocked the change/);
  assert.match(card._safeError({ code: 'replay_integrity' }), /safely blocked/);
  assert.match(card._safeError({ code: 'storage_failed' }), /saved durably/);
  dom.window.close();
}

{
  const { dom, card } = createCard(initial);
  await new Promise((resolve) => setTimeout(resolve, 30));
  let resolveFallback;
  card._callIntegration = async (command) => {
    if (command === 'pause_camera') return {};
    return new Promise((resolve) => { resolveFallback = resolve; });
  };
  const pending = card._runMutation('pause_camera', {});
  await new Promise((resolve) => setTimeout(resolve, 0));
  card._requestEpoch += 1;
  card._applyState({ ...initial, cameras: [{ camera_id: 'fresh', entity_id: null, name: 'Fresh' }] });
  resolveFallback({ ...initial, cameras: [{ camera_id: 'stale', entity_id: null, name: 'Stale' }] });
  await pending;

  assert.equal(card._cameras[0].camera_id, 'fresh');
  dom.window.close();
}

{
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: 'http://localhost/',
  });
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  dom.window.eval(source);
  dom.window.eval(source);
  assert.equal(
    dom.window.customCards.filter((entry) => entry.type === 'ha-frigate-privacy').length,
    1,
  );
  dom.window.close();
}

{
  const { dom, card } = createCard({
    ...initial,
    paused: { front: { camera_id: 'front', phase: 'active', active: false } },
  });
  await new Promise((resolve) => setTimeout(resolve, 30));

  assert.equal(card.shadowRoot.querySelector('[data-action="resume"]'), null);
  assert.equal(card._phaseSummary().phase, 'active');
  dom.window.close();
}

{
  const { dom, card } = createCard(initial);
  await new Promise((resolve) => setTimeout(resolve, 30));
  card._busy = true;
  card.disconnectedCallback();
  assert.equal(card._busy, false);
  dom.window.close();
}

{
  const { dom, card } = createCard({ ...initial, recovery_ready: false });
  await new Promise((resolve) => setTimeout(resolve, 30));

  assert.equal(card._recoveryReady, false);
  assert.equal(card.shadowRoot.querySelector('[data-action="pause-custom"]'), null);
  assert.match(card.shadowRoot.textContent, /Safely recovering state/);
  dom.window.close();
}

{
  const hostile = '<img src=x onerror=globalThis.__xss=1>';
  const { dom, card } = createCard({
    ...initial,
    last_operations: {
      front: {
        camera_id: 'front',
        name: hostile,
        source: 'manual',
        phase: 'active',
        active: false,
        observed_at: '2026-08-31T12:00:00+00:00',
        target_outcomes: { 'switch.front_detect': 'paused' },
        last_verified_actual_state: { 'switch.front_detect': 'on' },
      },
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 30));
  card.setActiveTab('state');

  assert.equal(card.shadowRoot.querySelector('.state-name')?.textContent, hostile);
  assert.equal(card.shadowRoot.querySelector('.state-name img'), null);
  assert.match(card.shadowRoot.textContent, /Last verified operation/);
  assert.match(card.shadowRoot.textContent, /switch\.front_detect/);
  dom.window.close();
}

assert.match(
  source,
  /set_schedule'[\s\S]{0,220}operation_id:this\._newOperationId\('schedule-/,
  'schedule mutations must carry bounded idempotency keys',
);
assert.match(
  source,
  /:host\s*\{[\s\S]{0,700}font-size:\s*15px;\s*line-height:\s*1\.55/,
  'the card must keep a readable base type size and line height',
);
assert.match(
  source,
  /\.state-meta\s*\{[^}]*font-size:\s*13px;[^}]*line-height:\s*1\.6/,
  'dense state metadata must remain readable',
);
assert.match(
  source,
  /@media \(max-width: 620px\)[^}]*[\s\S]{0,700}\.state-row, \.schedule-item \{ grid-template-columns: 1fr;/,
  'state and schedule rows must stop squeezing text on narrow cards',
);
assert.doesNotMatch(
  source,
  /\.state-meta\s*\{[^}]*font-size:\s*11px/,
  'state metadata must not regress to compressed 11px text',
);

console.log('truthful state, readable layout, and disconnect assertions passed');
