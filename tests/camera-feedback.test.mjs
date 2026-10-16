import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {JSDOM} from 'jsdom';
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
// Run the real pause/extension producer with its existing HA service/storage doubles.
// No handcrafted persisted fields: these regressions must follow backend changes.
const schedulePauses=JSON.parse(execFileSync('python3',['-B','-c',`
import asyncio, importlib.util, json
from pathlib import Path
spec = importlib.util.spec_from_file_location('recovery_fixture', Path('tests/test_restart_recovery.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
async def scenario(stream_type, initial_camera):
    hass, storage = m._Hass(), m._Storage()
    hass.states.values['camera.front'].state = initial_camera
    hass.states.values['camera.front'].attributes['supported_features'] = 0 if initial_camera == 'idle' else 2
    await m.control.async_pause_camera(hass, storage, 'front', stream_type=stream_type, duration_minutes=15, source='manual')
    await m.control.async_pause_camera(hass, storage, 'front', stream_type='all', source='schedule', schedule_id='B')
    return {'cameras':m.control.discover_frigate_cameras(hass), 'paused':storage.paused, 'last_operations':{}, 'schedules':[]}
async def main():
    return {'subset':await scenario('main', 'streaming'), 'toggled':await scenario('all', 'streaming'), 'neverToggled':await scenario('all', 'idle')}
print(json.dumps(asyncio.run(main())))
`],{cwd:new URL('..',import.meta.url),encoding:'utf8'}));
for(const path of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']){
 async function fixture(){
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window;
  const clock={now:Date.parse('2026-10-16T04:00:00Z'),timers:new Set()};
  w.Date.now=()=>clock.now;
  w.setInterval=(callback,delay)=>{const t={callback,delay};clock.timers.add(t);return t;};
  w.clearInterval=t=>clock.timers.delete(t);
  const created=[];
  w.customElements.define('hui-picture-entity-card',class extends w.HTMLElement {setConfig(config){this.previewConfig=config;}});
  w.loadCardHelpers=async()=>({createCardElement:config=>{const e=w.document.createElement('hui-picture-entity-card');e.setConfig(config);e.dataset.nativePreview=config.entity;created.push(e);return e;}});
  w.eval(readFileSync(new URL('../'+path,import.meta.url),'utf8'));
  const c=w.document.createElement('ha-frigate-privacy');c.setConfig({show_support:false});w.document.body.append(c);
  const record=(minutes,phase='paused')=>({active:true,phase,stream_type:'main',source:'manual',started_at:'2026-10-16T04:00:00Z',ends_at:new Date(clock.now+minutes*60000).toISOString(),target_outcomes:{'switch.front_recordings':phase==='paused'?'paused':'unavailable'},last_verified_actual_state:{'switch.front_recordings':phase==='paused'?'off':'unavailable'}});
  const state={cameras:[{camera_id:'front',entity_id:'camera.front',name:'Front',camera_state:'streaming',switches:[{suffix:'_recordings',state:'off'},{suffix:'_detect',state:'unknown'},{suffix:'_snapshots',state:'unavailable'}]},{camera_id:'back',entity_id:'camera.back',name:'Back',camera_state:'off',switches:[]}],paused:{front:record(5),back:{...record(10,'partial'),stream_type:'sub'}},last_operations:{},schedules:[]};
  const calls=[];const hass={language:'en',user:{id:'admin',is_admin:true},connection:{connected:true},config:{time_zone:'Europe/Warsaw'},states:{},callWS:async m=>{calls.push(m);return state;}};
  c.hass=hass;await tick();
  return {c,w,dom,clock,state,calls,hass,created,async advance(ms){clock.now+=ms;for(const t of clock.timers)if(t.delay===1000)t.callback();await tick();},close(){c.remove();w.close();}};
 }
 test(path+': independent server deadlines tick without DOM replacement or camera actions',async()=>{
  const f=await fixture();try{
   const a=f.c.shadowRoot.querySelector('[data-camera-countdown="front"]'),b=f.c.shadowRoot.querySelector('[data-camera-countdown="back"]');
   assert.ok(a,'Front needs a visible timer');assert.match(a.textContent,/05:00/);assert.match(b.textContent,/10:00/);
   const input=f.c.shadowRoot.querySelector('.input-minutes');input.focus();input.value='73';
   const count=f.calls.length;await f.advance(1000);
   assert.equal(f.c.shadowRoot.querySelector('[data-camera-countdown="front"]'),a);assert.match(a.textContent,/04:59/);assert.match(b.textContent,/09:59/);
   assert.equal(f.c.shadowRoot.activeElement,input);assert.equal(input.value,'73');assert.equal(f.calls.length,count);
   await f.advance(5*60000);assert.match(a.textContent,/Awaiting.*backend/i);assert.notEqual(f.c._paused.front.phase,'active');
   f.c.remove();assert.equal(f.clock.timers.size,0);f.w.document.body.append(f.c);assert.equal([...f.clock.timers].filter(t=>t.delay===1000).length,1);
  }finally{f.close();}
 });
 test(path+': per-camera phase, actual scope, channel evidence and semantic colors',async()=>{
  const f=await fixture();try{
   const front=f.c.shadowRoot.querySelector('[data-camera-feedback="front"]'),back=f.c.shadowRoot.querySelector('[data-camera-feedback="back"]');
   assert.ok(front);assert.match(front.textContent,/Recording/);assert.match(front.textContent,/switch.front_recordings.*paused/);assert.match(back.textContent,/Partial/);assert.match(back.textContent,/Detection/);
   for(const [channel,state] of [['video','on'],['recording','off'],['detection','unknown'],['snapshots','unavailable']])assert.equal(f.c.shadowRoot.querySelector(`[data-channel="${channel}"]`).dataset.channelState,state);
   f.c._applyState({...f.state,paused:{front:{active:true,phase:'pausing',stream_type:'main',ends_at:null}}});
   assert.match(f.c.shadowRoot.querySelector('[data-camera-feedback="front"]').textContent,/Pausing/);
   assert.doesNotMatch(f.c.shadowRoot.querySelector('[data-camera-countdown="front"]').textContent,/00:00|NaN/);
  }finally{f.close();}
 });
 test(path+': preview expands inline on demand, switches camera and is revoked with authority',async()=>{
  const f=await fixture();try{
   assert.equal(f.created.length,0);let dialogs=0;f.c.addEventListener('hass-more-info',()=>dialogs++);
   f.c.shadowRoot.querySelector('[data-preview-camera="camera.front"]').click();await tick();
   assert.equal(dialogs,0);assert.equal(f.created.length,1);assert.equal(f.created[0].previewConfig.entity,'camera.front');assert.equal(f.created[0].isConnected,true);
   assert.equal(f.c.shadowRoot.querySelector('[data-preview-camera="camera.front"]').getAttribute('aria-expanded'),'true');
   const before=f.created.length;await f.advance(1000);assert.equal(f.created.length,before);assert.equal(f.created[0].isConnected,true);
   f.c.shadowRoot.querySelector('[data-preview-camera="camera.back"]').click();await tick();assert.equal(f.created[0].isConnected,false);assert.equal(f.created[1].previewConfig.entity,'camera.back');
   f.c.hass={...f.hass,user:{id:'household',is_admin:false}};assert.equal(f.created[1].isConnected,false);assert.equal(f.c.shadowRoot.querySelector('[data-preview-host]'),null);
   assert.equal(f.calls.filter(m=>!m.type.endsWith('/get_state')).length,0);
  }finally{f.close();}
 });
 test(path+': closed or identity-stale helper cannot mount a late preview',async()=>{
  const f=await fixture();try{
   let resolve;f.w.loadCardHelpers=()=>new Promise(r=>{resolve=r;});
   f.c.shadowRoot.querySelector('[data-preview-camera="camera.front"]').click();
   f.c.shadowRoot.querySelector('[data-preview-camera="camera.front"]').click();
   resolve({createCardElement:()=>{throw Error('stale helper must not create');}});await tick();
   assert.equal(f.c.shadowRoot.querySelector('[data-preview-host]'),null);
  }finally{f.close();}
 });
 test(path+': pending Start identifies only requested cameras without claiming applied success',async()=>{
  const f=await fixture();try{
   f.c._applyState({...f.state,paused:{}});f.c._selectedCameras=new Set(['front']);
   let finish;f.c._hass.callWS=m=>m.type.endsWith('/get_state')?Promise.resolve({...f.state,paused:{}}):new Promise(r=>{finish=r;});
   const pending=f.c._pause();
   assert.match(f.c.shadowRoot.querySelector('[data-camera-feedback="front"]').textContent,/Applying.*unconfirmed/);
   assert.equal(f.c.shadowRoot.querySelector('[data-camera-feedback="back"]'),null);
   finish({ok:false,phase:'error'});await pending;
   assert.equal(f.c.shadowRoot.querySelector('[data-camera-pending]'),null);
  }finally{f.close();}
 });
 test(path+': preview failure stays visible until an explicit retry; unavailable capture is not success',async()=>{
  const f=await fixture();try{
   let calls=0;f.w.loadCardHelpers=async()=>{calls++;throw Error('PRIVATE_ERROR_CANARY');};
   f.c.shadowRoot.querySelector('[data-preview-camera="camera.front"]').click();await tick();
   assert.match(f.c.shadowRoot.querySelector('[data-preview-host]').textContent,/unavailable/);
   assert.doesNotMatch(f.c.shadowRoot.textContent,/PRIVATE_ERROR_CANARY/);
   f.c._updateUI();f.c.hass=f.hass;await tick();assert.equal(calls,1,'normal HA updates must not retry preview after failure');
   f.c.shadowRoot.querySelector('[data-preview-camera="camera.front"]').click();f.c.shadowRoot.querySelector('[data-preview-camera="camera.front"]').click();await tick();assert.equal(calls,2);
  }finally{f.close();}
 });
 test(path+': mixed camera results keep confirmed success and error separate',async()=>{
  const f=await fixture();try{
   f.c._applyState({...f.state,paused:{}});
   f.c._hass.callWS=async m=>m.type.endsWith('/get_state')?{...f.state,paused:{front:f.state.paused.front}}:{ok:false,phase:'partial',results:[{camera_id:'front',paused:true,phase:'paused'},{camera_id:'back',paused:false,phase:'error'}]};
   assert.equal(await f.c._pause(),false);assert.equal(f.c._mutationOutcome.code,'partial');
   assert.equal(f.c.shadowRoot.querySelector('[data-camera-feedback="front"] [data-result-state]').dataset.resultState,'success');
   assert.equal(f.c.shadowRoot.querySelector('[data-camera-feedback="back"] [data-result-state]').dataset.resultState,'error');
   f.c._hass.callWS=async m=>m.type.endsWith('/get_state')?f.state:{ok:false,phase:'partial',results:[{camera_id:'front',paused:true,phase:'paused'}]};
   await f.c._pause();assert.equal(f.c.shadowRoot.querySelector('[data-camera-feedback="back"] [data-result-state]').dataset.resultState,'unconfirmed');
  }finally{f.close();}
 });
 test(path+': reserved camera slugs never inherit phantom operations',async()=>{
  const f=await fixture();try{
   const state={...f.state,cameras:[
    {camera_id:'constructor',entity_id:'camera.constructor',name:'Constructor',state:'on',switches:[]},
    {camera_id:'__proto__',entity_id:'camera.__proto__',name:'Prototype',state:'on',switches:[]}],paused:{},last_operations:{}};
   f.c._applyState(state);
   assert.equal(f.c.shadowRoot.querySelectorAll('[data-camera-feedback]').length,0);
   const own=JSON.parse('{"__proto__":{"active":true,"phase":"paused","stream_type":"main","ends_at":null}}');
   f.c._hass.callWS=async m=>m.type.endsWith('/get_state')?{...state,paused:own}:{ok:true,phase:'paused',results:[{camera_id:'__proto__',paused:true,phase:'paused'}]};
   assert.equal(await f.c._runMutation('pause_camera',{cameras:['__proto__']}),true);
   assert.equal(f.c.shadowRoot.querySelector('[data-camera-feedback="__proto__"] [data-result-state]').dataset.resultState,'success');
   assert.equal(f.c.shadowRoot.querySelector('[data-camera-feedback="constructor"]'),null);
   f.c._applyState({...state,paused:{},last_operations:JSON.parse('{"constructor":{"phase":"active","stream_type":"main"}}')});
   assert.equal(f.c.shadowRoot.querySelector('[data-camera-feedback="constructor"] [data-camera-countdown]'),null);
  }finally{f.close();}
 });
 test(path+': tile distinguishes pause from resume evidence and requested from applied scope',async()=>{
  const f=await fixture();try{
   const restored={active:false,phase:'active',stream_type:'main',target_outcomes:{'switch.front_recordings':'paused'},resume_target_outcomes:{'switch.front_recordings':'active'},last_verified_actual_state:{'switch.front_recordings':'on'}};
   f.c._applyState({...f.state,paused:{},last_operations:{front:restored}});
   const tile=f.c.shadowRoot.querySelector('[data-camera-feedback="front"]');assert.match(tile.textContent,/Resume.*switch.front_recordings.*active/s);assert.match(tile.textContent,/Pause.*switch.front_recordings.*paused/s);
   f.c._applyState({...f.state,paused:{front:{...f.state.paused.front,phase:'pausing'}}});
   assert.match(f.c.shadowRoot.querySelector('[data-camera-feedback="front"]').textContent,/Requested scope/);assert.doesNotMatch(f.c.shadowRoot.querySelector('[data-camera-feedback="front"]').textContent,/Applied scope/);
  }finally{f.close();}
 });
 test(path+': Everything does not imply confirmed video stop on a camera without direct video control',async()=>{
  const f=await fixture();try{
   // The actual producer marks every registered Frigate camera as can_toggle;
   // whether this action switched video is persisted separately in its plan.
   const state={...f.state,cameras:[{...f.state.cameras[0],camera_can_toggle:true,camera_state:'idle'}],paused:{front:{...f.state.paused.front,stream_type:'all',camera_planned:false}}};
   f.c._applyState(state);
   const tile=f.c.shadowRoot.querySelector('[data-camera-feedback="front"]');
   assert.match(tile.textContent,/Requested scope: Everything/);assert.doesNotMatch(tile.textContent,/Applied scope/);
   assert.match(tile.querySelector('[data-video-stop-unconfirmed]')?.textContent||'',/video stop is not confirmed/i);
   assert.equal(f.c.shadowRoot.querySelector('[data-channel="video"]').dataset.channelState,'idle');
  }finally{f.close();}
 });
 test(path+': real schedule extension separates original requested subset from additional coverage',async()=>{
  const f=await fixture();try{
   const state=schedulePauses.subset,record=state.paused.front;
   assert.equal(record.stream_type,'main');assert.equal(record.source,'manual');assert.equal(record.extension,true);
   assert.deepEqual(record.switches,['switch.front_recordings','switch.front_detect']);assert.equal(record.camera_toggled,true);
   f.c._applyState(state);
   const tile=f.c.shadowRoot.querySelector('[data-camera-feedback="front"]');
   assert.match(tile.textContent,/Requested scope: Recording/);assert.doesNotMatch(tile.textContent,/Applied scope/);
   assert.match(tile.querySelector('[data-schedule-coverage]')?.textContent||'',/schedule.*confirmed targets/i);
   assert.match(tile.textContent,/Pause.*switch.front_detect: paused/s);assert.match(tile.textContent,/Pause.*camera.front: paused/s);
  }finally{f.close();}
 });
 test(path+': real schedule extension retains confirmed idle video stop from the original pause',async()=>{
  const f=await fixture();try{
   const state=schedulePauses.toggled,record=state.paused.front;
   assert.equal(record.phase,'paused');assert.equal(record.camera_planned,false);assert.equal(record.camera_toggled,true);
   assert.equal(record.target_outcomes['camera.front'],'paused');assert.equal(record.last_verified_actual_state['camera.front'],'idle');
   assert.equal(state.cameras[0].camera_state,'idle');
   f.c._applyState(state);
   const tile=f.c.shadowRoot.querySelector('[data-camera-feedback="front"]');
   assert.equal(tile.querySelector('[data-video-stop-unconfirmed]'),null);
   assert.doesNotMatch(tile.textContent,/video was not switched|video stop is not confirmed/i);
   assert.match(tile.textContent,/Pause.*camera.front: paused/s);
   // Missing evidence or a newly streaming camera cannot inherit the prior proof.
   for(const invalid of [
    {...state,cameras:[{...state.cameras[0],camera_state:'streaming'}]},
    {...state,paused:{front:{...record,target_outcomes:{}}}},
    {...state,paused:{front:{...record,last_verified_actual_state:{}}}},
   ]){
    f.c._applyState(invalid);
    assert.ok(f.c.shadowRoot.querySelector('[data-video-stop-unconfirmed]'));
   }
  }finally{f.close();}
 });
 test(path+': real schedule extension preserves the warning when idle video was never toggled',async()=>{
  const f=await fixture();try{
   const state=schedulePauses.neverToggled,record=state.paused.front;
   assert.equal(record.camera_planned,false);assert.equal(record.camera_toggled,false);assert.equal(record.phase,'paused');
   f.c._applyState(state);
   assert.match(f.c.shadowRoot.querySelector('[data-video-stop-unconfirmed]')?.textContent||'',/video stop is not confirmed/i);
  }finally{f.close();}
 });
 test(path+': unrecognized channel states cannot inherit Object prototype entries',async()=>{
  const f=await fixture();try{
   f.c._applyState({...f.state,cameras:[{...f.state.cameras[0],camera_state:'constructor',switches:[{suffix:'_recordings',state:'__proto__'},{suffix:'_detect',state:'toString'}]}]});
   for(const name of ['video','recording','detection']){
    const badge=f.c.shadowRoot.querySelector(`[data-channel="${name}"]`);assert.equal(badge.dataset.channelState,'unknown');assert.match(badge.textContent,/Unknown/);
   }
  }finally{f.close();}
 });
}
