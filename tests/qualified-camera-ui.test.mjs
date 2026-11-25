import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
for (const source of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']) {
 test(source+': qualified camera IDs survive history, selection and quick actions',()=>{
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',url:'http://localhost/'}),w=dom.window;
  w.eval(readFileSync(new URL('../'+source,import.meta.url),'utf8'));
  const card=w.document.createElement('ha-frigate-privacy');card.setConfig({cameras:['one:front']});
  card._cameras=[{camera_id:'one:front',entity_id:'camera.front',name:'Front'},{camera_id:'two:front',entity_id:'camera.front_2',name:'Other'}];
  const row={id:'a'.repeat(64),camera_id:'one:front',generation:1,started_at:'2026-10-12T18:00:00Z',ended_at:null,planned_ends_at:null,observed_at:null,phase:'partial',source:'manual',reason:'pause_incomplete',end_reason:null,verified_restore:false,duration_seconds:null,channels:[{channel:'detection',target:'switch.front_detect',pause_outcome:'paused',restore_outcome:'unknown',observed_state:'off'}],unknown_channels:[],evidence_scope:'transition_intent'};
  const payload={schema:1,status:'ready',durability:'confirmed',periods:[row]};
  const projection=card._validatePeriods(payload);assert.equal(projection.rows[0].camera_id,'one:front');
  card._periods=projection.rows;card._periodSelected=row.id;card._periodInfo=projection.info;
  assert.match(card._buildHistoryTab(),/one:front/);assert.match(card._buildHistoryTab(),/switch.front_detect/);
  const restored={...row,camera_id:'front',phase:'active',ended_at:'2026-10-12T19:00:00Z',duration_seconds:3600,end_reason:'admin_request',verified_restore:true,channels:[{channel:'detection',target:'switch.front_detect',pause_outcome:'paused',restore_outcome:'active',restore_expected:true,observed_state:'on'}]};
  assert.equal(card._validatePeriods({...payload,periods:[restored]}).rows[0].verified_restore,true);
  assert.throws(()=>card._validatePeriods({...payload,periods:[{...restored,camera_id:'one:front'}]}));
  assert.equal(card._isVisibleCameraId('one:front'),true);assert.equal(card._isVisibleCameraId('two:front'),false);
  assert.deepEqual(Array.from(card._selectedCameraIds()),['one:front']);
  let sent;card._runMutation=(command,data)=>{sent={command,data};};card._quickPause('one:front',15);assert.equal(sent.data.cameras[0],'one:front');
  for(const id of ['',':front','one:','one:two:front','ONE:front','one/front','a'.repeat(256),'a'.repeat(254)+':b']) assert.throws(()=>card._validatePeriods({...payload,periods:[{...row,camera_id:id}]}));
  assert.equal(card._validatePeriods({...payload,periods:[{...row,camera_id:'a'.repeat(253)+':b'}]}).rows.length,1);
  dom.window.close();
 });
}
