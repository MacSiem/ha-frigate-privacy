import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read = path => readFileSync(new URL('../'+path, import.meta.url), 'utf8');
test('release version agrees across manifest, cache-bust constant and card copies', () => {
 const version=JSON.parse(read('custom_components/ha_frigate_privacy/manifest.json')).version;
 assert.equal(version,'6.6.0');
 assert.match(read('custom_components/ha_frigate_privacy/const.py'),new RegExp(`^VERSION = "${version.replaceAll('.', '\\.')}"$`,'m'));
 assert.match(read('custom_components/ha_frigate_privacy/frontend.py'),/return f"\{CARD_URL\}\?v=\{VERSION\}"/);
 const card=read('ha-frigate-privacy.js');
 assert.ok(card.startsWith(`/* Frigate Privacy v${version} `));
 assert.equal(card,read('custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js'));
});
