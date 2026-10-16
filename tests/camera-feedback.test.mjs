import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
for(const path of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']){
 async function fixture(){
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window;
  const clock={now:Date.parse('2026-10-16T04:00:00Z'),timers:new Set()};
  w.Date.now=()=>clock.now;
  w.setInterval=(callback,delay)=>{const t={callback,delay};clock.timers.add(t);return t;};
  w.clearInterval=t=>clock.timers.delete(t);
  const created=[];
  w.loadCardHelpers=async()=>({createCardElement:config=>{const e=w.document.createElement('div');e.dataset.nativePreview=config.entity;e.previewConfig=config;created.push(e);return e;}});
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
}
