import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const tick=()=>new Promise(r=>setTimeout(r,0));
async function fixture(config={}){
 const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window;
 w.eval(readFileSync(new URL('../ha-frigate-privacy.js',import.meta.url),'utf8'));
 const c=w.document.createElement('ha-frigate-privacy');c.setConfig({show_support:false,...config});w.document.body.append(c);
 const calls=[],state={cameras:[{camera_id:'front',entity_id:'camera.front',name:'Front',switches:[]},{camera_id:'garden',entity_id:'camera.garden',name:'Garden',switches:[]}],schedules:[],paused:{},last_operations:{},recovery_ready:true};
 const hass={language:'en',user:{id:'owner',is_admin:true},connection:{connected:true},config:{time_zone:'UTC'},states:{},callWS:async m=>{calls.push(m);if(m.type.endsWith('/get_state'))return state;
  const action=m.type.split('/').at(-1),id=m.cameras[0];
  if(action==='pause_camera'){state.paused[id]={active:true,phase:'paused',stream_type:m.stream_type,started_at:'2026-10-18T10:00:00Z',ends_at:'2026-10-18T10:15:00Z'};return {ok:true,phase:'paused',results:[{camera_id:id,paused:true,phase:'paused'}]};}
  if(action==='extend_privacy'){state.paused[id].ends_at='2026-10-18T10:30:00Z';return {ok:true,phase:'paused',results:[{camera_id:id,extended:true,phase:'paused',ends_at:'2026-10-18T10:30:00Z'}]};}
  if(action==='resume_camera'){delete state.paused[id];return {ok:true,phase:'active',results:[{camera_id:id,resumed:true,phase:'active'}]};}
  throw Error('Unexpected action');}};
 c.hass=hass;await tick();return{w,c,r:c.shadowRoot,hass,calls,state,close(){c.remove();w.close();}};
}
test('one camera quick timer ignores bulk selection; extension retains recording scope',async()=>{
 const f=await fixture();try{
  f.r.querySelector('[data-camera="garden"]').click();f.r.querySelector('[data-scope="main"]').click();
  const quick=f.r.querySelector('[data-quick-camera="front"][data-quick-minutes="15"]');assert.ok(quick,'quick action belongs to the camera');quick.click();await tick();
  const pause=f.calls.find(m=>m.type.endsWith('/pause_camera'));assert.deepEqual(Array.from(pause.cameras),['front']);assert.equal(pause.duration_minutes,15);assert.equal(pause.stream_type,'main');assert.ok(pause.operation_id);assert.equal(f.state.paused.garden,undefined);
  const extend=f.r.querySelector('[data-extend-camera="front"]');assert.ok(extend);extend.click();await tick();
  assert.equal(f.state.paused.front.stream_type,'main');assert.equal(f.state.paused.front.ends_at,'2026-10-18T10:30:00Z');assert.equal(f.calls.filter(m=>m.type.endsWith('/pause_camera')).length,1);
  assert.equal(f.r.querySelector('[data-action-result] [data-result-state]').dataset.resultState,'success');
 }finally{f.close();}
});
test('resume requires an explicit camera-naming confirmation and cancel does not mutate',async()=>{
 const f=await fixture();try{
  f.state.paused.front={active:true,phase:'paused',ends_at:'2026-10-18T10:15:00Z',stream_type:'main'};f.c._applyState(f.state);
  f.r.querySelector('[data-resume-camera="front"]').click();let dialog=f.r.querySelector('[data-resume-confirm]');assert.ok(dialog);assert.match(dialog.textContent,/Front/);assert.match(dialog.textContent,/privacy/i);assert.equal(f.calls.filter(m=>m.type.endsWith('/resume_camera')).length,0);
  dialog.querySelector('[data-resume-cancel]').click();assert.equal(f.calls.filter(m=>m.type.endsWith('/resume_camera')).length,0);
  f.r.querySelector('[data-action="resume"]').click();dialog=f.r.querySelector('[data-resume-confirm]');dialog.querySelector('[data-resume-accept]').click();await tick();assert.equal(f.calls.filter(m=>m.type.endsWith('/resume_camera')).length,1);assert.equal(f.state.paused.front,undefined);
 }finally{f.close();}
});
test('camera filter scopes bulk actions and compact uses narrow grid without exposing another camera',async()=>{
 const f=await fixture({cameras:['front'],compact:true,tabs:['control','state'],default_tab:'state',show_help:false});try{
  assert.equal(f.c._activeTab,'state');assert.equal(f.r.querySelector('[data-intro]'),null);assert.deepEqual(Array.from(f.r.querySelectorAll('[data-tab]'),e=>e.dataset.tab),['control','state']);
  f.c.setActiveTab('control');assert.equal(f.r.querySelector('[data-camera="garden"]'),null);assert.ok(f.c.getGridOptions().min_columns<=3);
  f.r.querySelector('[data-action="pause-custom"]')?.click();await tick();
  for(const m of f.calls.filter(m=>m.type.endsWith('/pause_camera')))assert.deepEqual(Array.from(m.cameras),['front']);
  assert.throws(()=>f.c.setConfig({tabs:['control'],default_tab:'history'}),/tab/i);
 }finally{f.close();}
});
test('visual editor saves all applicable options, preserves unknown keys, rejects hidden default',async()=>{
 const f=await fixture();try{
  const e=f.w.document.createElement('ha-frigate-privacy-editor');e.hass=f.hass;e.setConfig({title:'Example',future:{keep:true}});f.w.document.body.append(e);let config;e.addEventListener('config-changed',v=>{config=v.detail.config;e.setConfig(config);});
  const compact=e.shadowRoot.querySelector('[data-config="compact"]');assert.ok(compact);compact.checked=true;compact.dispatchEvent(new f.w.Event('change'));assert.equal(config.compact,true);assert.equal(config.future.keep,true);
  const cameras=e.shadowRoot.querySelector('[data-config="cameras"]');assert.ok(cameras);cameras.value='front, garden';cameras.dispatchEvent(new f.w.Event('change'));assert.deepEqual(Array.from(config.cameras),['front','garden']);
  assert.ok(e.shadowRoot.querySelector('[data-config="default_tab"]'));assert.ok(e.shadowRoot.querySelector('[data-config="show_help"]'));assert.ok(e.shadowRoot.querySelector('[data-config="show_support"]'));
 }finally{f.close();}
});

test('compact card is one camera tile with quick actions and an explicit path to full controls',async()=>{
 const f=await fixture({compact:true,show_help:false});try{
  assert.equal(f.r.querySelectorAll('.camera-tile').length,1,'compact shows one camera at a time');
  assert.equal(f.r.querySelector('[data-action="pause-custom"]'),null,'bulk controls belong to the expanded view');
  const open=f.r.querySelector('[data-open-full]');assert.ok(open);open.click();assert.ok(f.r.querySelector('[data-action="pause-custom"]'));assert.ok(f.r.querySelector('[data-close-full]'));
 }finally{f.close();}
});

test('ordinary state refresh keeps the same-account resume confirmation usable',async()=>{
 const f=await fixture();try{
  f.state.paused.front={active:true,phase:'paused',ends_at:'2026-10-18T10:15:00Z',stream_type:'main'};f.c._applyState(f.state);
  f.r.querySelector('[data-resume-camera="front"]').click();await f.c._connectIntegration();
  f.r.querySelector('[data-resume-accept]').click();await tick();
  assert.equal(f.calls.filter(m=>m.type.endsWith('/resume_camera')).length,1,'ordinary reads must not revoke a same-account confirmation');
 }finally{f.close();}
});

for (const [name,config,selector] of [
 ['compact camera',{compact:true,cameras:['front']},'[data-resume-camera="front"]'],
 ['full camera',{},'[data-resume-camera="front"]'],
 ['bulk',{},'[data-action="resume"]'],
 ['state retry',{},'[data-retry-camera="front"]'],
]) test(`cancel resume returns keyboard focus to its ${name} trigger without mutations`,async()=>{
 const f=await fixture(config);try{
  f.state.paused.front={active:true,phase:name==='state retry'?'partial':'paused',ends_at:'2026-10-18T10:15:00Z',stream_type:'main'};f.c._applyState(f.state);
  if(name==='state retry')f.c.setActiveTab('state');
  const origin=f.r.querySelector(selector);assert.ok(origin);origin.focus();origin.click();
  assert.ok(f.r.querySelector('[data-resume-confirm]'));
  f.r.querySelector('[data-resume-cancel]').click();
  assert.equal(f.r.activeElement,f.r.querySelector(selector),'the initiating control remains the keyboard return point after dialog cancellation');
  assert.equal(f.calls.filter(m=>m.type.endsWith('/resume_camera')).length,0);
 }finally{f.close();}
});
