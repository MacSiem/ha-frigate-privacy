'use strict';
// Verify the actual shipped closures, not only the presence of shared files.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const files=['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js'];
const rootSource=fs.readFileSync(path.join(root,files[0]),'utf8');
for(const file of files){
  const source=fs.readFileSync(path.join(root,file),'utf8');
  assert.equal(source,rootSource,'manual and integration cards must match');
  for(const [name,marker] of [['ha-tools-format.js','HA_FORMAT_UI'],['ha-tools-lists.js','HA_LIST_UI'],['ha-tools-card-ui.js','HA_CARD_UI']]){
    const canonical=fs.readFileSync(path.join(root,'shared',name),'utf8').split('// Node tests use the canonical factory;')[0].trimEnd();
    const start=`// ${marker}_START\n`,end=`\n// ${marker}_END`;
    assert.equal(source.split(start).length,2,'one closure marker required');
    assert.equal(source.split(start)[1].split(end)[0],canonical,`${file}: ${name} must be the actual canonical factory`);
  }
}
console.log('Shared format/list factories and both shipped cards are exact');
