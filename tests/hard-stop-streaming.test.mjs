import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../ha-frigate-privacy.js', import.meta.url), 'utf8');

assert.match(
  source,
  /callService\('camera',\s*cameraAction,\s*\{\s*entity_id:\s*camId\s*\}\)/s,
  'full camera pause/resume should call camera.turn_off/turn_on for the selected camera entity',
);

assert.match(
  source,
  /const hardStopCamera = \(streamType \|\| 'all'\) === 'all'/,
  'hard camera stop should be limited to the full all-stream privacy mode',
);

assert.match(
  source,
  /const allCameras = this\._cameras\.map\(c => c\.entity_id\)/,
  'timer-expiry automation should know which camera entities need camera.turn_on',
);

assert.match(
  source,
  /\{\s*action:\s*'camera\.turn_on',\s*target:\s*\{\s*entity_id:\s*allCameras\s*\}\s*\}/s,
  'timer-expiry automation should turn camera entities back on when the browser is closed',
);

assert.match(
  source,
  /\{\s*action:\s*'camera\.turn_off',\s*target:\s*\{\s*entity_id:\s*allCameras\s*\}\s*\}/s,
  'schedule automation should stop camera streams, not only Frigate feature switches',
);
