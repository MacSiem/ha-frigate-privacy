import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
for (const path of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']) {
 test(path+': individual scopes follow selected cameras and export the selected scope', async()=>{
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',url:'http://localhost/'}),w=dom.window;
  w.eval(readFileSync(new URL('../'+path,import.meta.url),'utf8'));
  const card=w.document.createElement('ha-frigate-privacy'),calls=[];
  const state={cameras:[{camera_id:'front',name:'Front',feature_scopes:['recordings','camera','audio_detection'],switches:[{suffix:'_audio_detection',state:'on'}]},{camera_id:'back',name:'Back',feature_scopes:['recordings'],switches:[]}],schedules:[],paused:{},last_operations:{}};
  card.setConfig({show_support:false});w.document.body.append(card);
  card.hass={language:'en',user:{id:'a',is_admin:true,is_active:true},connection:{connected:true},config:{},states:{},callWS:m=>{calls.push(m);return Promise.resolve(m.type.endsWith('/get_state')?state:{ok:true});}};
  await new Promise(r=>setTimeout(r,0));const root=card.shadowRoot;
  assert.equal(root.querySelector('[data-scope="camera"]').disabled,true);
  root.querySelector('[data-camera="front"]').click();assert.equal(root.querySelector('[data-scope="camera"]').disabled,false);
  root.querySelector('[data-scope="camera"]').click();
  assert.equal(root.querySelector('[data-quick-camera="back"]').disabled,true);
  assert.match(root.textContent,/Listening via go2rtc: Unknown/);assert.match(root.textContent,/Recording audio: Unknown/);assert.match(root.textContent,/go2rtc/);
  assert.equal(card._quickPause('back',15),false);
  assert.match(card._actionExample('pause'),/stream_type: camera/);
  root.querySelector('[data-action="pause-custom"]').click();await new Promise(r=>setTimeout(r,0));
  const pause=calls.find(m=>m.type.endsWith('/pause_camera'));assert.equal(pause.stream_type,'camera');assert.deepEqual(Array.from(pause.cameras),['front']);
  root.querySelector('[data-camera="__all__"]').click();assert.equal(card._pauseStreamType,'camera');assert.equal(root.querySelector('[data-action="pause-custom"]').disabled,true);assert.equal(root.querySelector('[data-scope-unavailable]').hidden,false);assert.doesNotMatch(card._actionExample(),/stream_type/);
  card.remove();dom.window.close();
 });
}

for (const path of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']) {
 test(path+': audio scope remains selected and cannot broaden after camera or capability change', async()=>{
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',url:'http://localhost/'}),w=dom.window;
  w.eval(readFileSync(new URL('../'+path,import.meta.url),'utf8'));
  const card=w.document.createElement('ha-frigate-privacy'),calls=[];
  const state={cameras:[{camera_id:'front',name:'Front',feature_scopes:['audio_detection','motion','review_alerts','review_detections'],switches:[{suffix:'_audio_detection',state:'on'},{suffix:'_motion',state:'off'},{suffix:'_review_alerts',state:'on'},{suffix:'_review_detections',state:'off'}]},{camera_id:'back',name:'Back',feature_scopes:[],switches:[]}],schedules:[],paused:{},last_operations:{}};
  card.setConfig({show_support:false});w.document.body.append(card);
  card.hass={language:'en',user:{id:'a',is_admin:true,is_active:true},connection:{connected:true},config:{},states:{},callWS:m=>{calls.push(m);return Promise.resolve(m.type.endsWith('/get_state')?state:{ok:true});}};
  await new Promise(r=>setTimeout(r,0));let root=card.shadowRoot;
  assert.match(root.textContent,/Motion: Off/);assert.match(root.textContent,/Review alerts: On/);assert.match(root.textContent,/Review detections: Off/);
  root.querySelector('[data-camera="front"]').click();root.querySelector('[data-scope="audio_detection"]').click();
  root.querySelector('[data-camera="back"]').click();root.querySelector('[data-camera="front"]').click();
  assert.equal(card._pauseStreamType,'audio_detection');assert.equal(root.querySelector('[data-action="pause-custom"]').disabled,true);
  assert.equal(card._pause(),false);assert.equal(card._quickPause('back',15),false);
  card._applyState(state);root=card.shadowRoot;assert.equal(card._pauseStreamType,'audio_detection');assert.equal(root.querySelector('[data-action="pause-custom"]').disabled,true);
  card._selectedCameras=new Set(['front']);state.cameras[0].feature_scopes=[];card._applyState(state);assert.equal(card._pauseStreamType,'audio_detection');assert.equal(card._pause(),false);
  state.cameras.shift();card._applyState(state);assert.equal(card._pause(),false);assert.equal(card._selectedCameraIds().length,0);
  card.setActiveTab('actions');root=card.shadowRoot;assert.equal(root.querySelector('[data-action="copy-example"]').disabled,true);assert.doesNotMatch(root.querySelector('.action-example').value,/stream_type/);
  assert.equal(calls.filter(m=>m.type.endsWith('/pause_camera')).length,0);
  card.remove();dom.window.close();
 });
}
