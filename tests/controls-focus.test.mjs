import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const tick=()=>new Promise(r=>setTimeout(r,0));
for(const sourcePath of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']){
 async function fixture(width=390){
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window,observers=[];
  w.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.closed=true;}};
  w.eval(readFileSync(new URL('../'+sourcePath,import.meta.url),'utf8'));
  const c=w.document.createElement('ha-frigate-privacy');c.getBoundingClientRect=()=>({width});
  let resolve,reject;const calls=[];const state={cameras:[{camera_id:'front',entity_id:'camera.front',name:'Front'}],schedules:[{id:'stable-a',label:'Night',enabled:true,days:[1],startHour:18,startMin:0,endHour:20,endMin:0}],paused:{},last_operations:{},recovery_ready:true};
  const hass={language:'en',themes:{darkMode:false},config:{time_zone:'Europe/Warsaw'},user:{id:'admin',is_admin:true,is_active:true},connection:{connected:true},states:{},callWS:m=>{calls.push(m);return m.type.endsWith('/get_state')?Promise.resolve(state):new Promise((yes,no)=>{resolve=yes;reject=no;});}};
  c.setConfig({show_support:false});w.document.body.append(c);c.hass=hass;await tick();
  return{dom,w,c,r:c.shadowRoot,hass,calls,state,observers,resolve(v={ok:true}){resolve(v);},reject(){reject({code:'storage_failed'});},resize(n){width=n;observers.filter(o=>!o.closed).forEach(o=>o.callback());},close(){c.remove();w.close();}};
 }
 test(sourcePath+': compact navigation retains all six tabs and focus through resize',async()=>{const f=await fixture(260);try{
  let p=f.r.querySelector('[data-tab-picker]');assert.ok(p);assert.equal(p.hidden,false);assert.deepEqual(Array.from(p.options,o=>o.value),['control','schedule','state','history','actions','info']);
  for(const tab of ['schedule','state','history','actions','info','control']){p=f.r.querySelector('[data-tab-picker]');p.value=tab;p.dispatchEvent(new f.w.Event('change'));assert.equal(f.c._activeTab,tab);assert.equal(f.r.activeElement,f.r.querySelector('[data-tab-picker]'));}
  f.resize(900);assert.equal(f.r.activeElement.dataset.tab,'control');f.resize(260);assert.equal(f.r.activeElement,f.r.querySelector('[data-tab-picker]'));assert.equal(f.observers.filter(o=>!o.closed).length,1);f.c.remove();assert.equal(f.observers.filter(o=>!o.closed).length,0);f.w.document.body.append(f.c);assert.equal(f.observers.filter(o=>!o.closed).length,1);
 }finally{f.close();}});
 for(const outcome of ['success','error','partial'])test(sourcePath+': pause restores keyboard origin after '+outcome,async()=>{const f=await fixture();try{
  const b=f.r.querySelector('[data-action="pause-custom"]');b.focus();b.click();assert.equal(f.r.querySelector('[data-action="pause-custom"]').disabled,true);
  if(outcome==='error')f.reject();else f.resolve({ok:outcome==='success',phase:outcome});await tick();assert.equal(f.r.activeElement?.dataset.action,'pause-custom');assert.equal(f.calls.filter(m=>m.type.endsWith('/pause_camera')).length,1);
 }finally{f.close();}});
 test(sourcePath+': pending action never steals outside focus or crosses identity',async()=>{const f=await fixture();try{
  let b=f.r.querySelector('[data-action="pause-custom"]');b.focus();b.click();const outside=f.w.document.createElement('input');f.w.document.body.append(outside);outside.focus();f.resolve();await tick();assert.equal(f.w.document.activeElement,outside);
  b=f.r.querySelector('[data-action="pause-custom"]');b.focus();b.click();f.c.hass={...f.hass,user:{id:'other',is_admin:false}};f.resolve();await tick();assert.equal(f.r.querySelector('[data-action="pause-custom"]'),null);assert.equal(f.r.activeElement,null);
 }finally{f.close();}});
 test(sourcePath+': schedule save restores origin; deleted schedule falls back without focusing shifted row',async()=>{const f=await fixture();try{
  f.c.setActiveTab('schedule');let b=f.r.querySelector('[data-action="save-schedule"]');b.focus();b.click();f.resolve();await tick();assert.equal(f.r.activeElement?.dataset.action,'save-schedule');
  b=f.r.querySelector('[data-schedule-delete="0"]');b.focus();b.click();f.state.schedules=[{...f.state.schedules[0],id:'stable-b'}];f.resolve();await tick();assert.ok(f.r.activeElement?.matches('[data-tab="schedule"],[data-tab-picker]'));assert.notEqual(f.r.activeElement?.dataset.scheduleDelete,'0');
 }finally{f.close();}});
 test(sourcePath+': switching tabs while pending preserves the new focus',async()=>{const f=await fixture();try{f.r.querySelector('[data-action="pause-custom"]').focus();f.r.querySelector('[data-action="pause-custom"]').click();const tab=f.r.querySelector('[data-tab="info"]');tab.focus();tab.click();f.resolve();await tick();assert.equal(f.r.activeElement?.dataset.tab,'info');}finally{f.close();}});
 test(sourcePath+': editor echo, hass, empty title and reconnect keep node and backward selection',async()=>{const f=await fixture();try{
  const e=f.w.document.createElement('ha-frigate-privacy-editor');e.setConfig({title:'Example',future:{keep:true}});f.w.document.body.append(e);let count=0;e.addEventListener('config-changed',event=>{count++;e.setConfig(event.detail.config);});
  const input=e.shadowRoot.querySelector('input');input.focus();input.value='A & <B>';input.setSelectionRange(1,5,'backward');input.dispatchEvent(new f.w.Event('input'));assert.equal(e.shadowRoot.querySelector('input'),input);assert.equal(e.shadowRoot.activeElement,input);assert.equal(input.selectionDirection,'backward');
  e.hass={language:'pl'};assert.equal(e.shadowRoot.activeElement,input);assert.equal(input.selectionStart,1);assert.equal(input.selectionDirection,'backward');assert.ok(e.shadowRoot.textContent.includes('Tytuł'));
  input.value='';input.dispatchEvent(new f.w.Event('input'));assert.equal(input.value,'');e.setConfig({...e._config,title:'External'});assert.equal(input.value,'External');e.remove();f.w.document.body.append(e);input.value='Once';input.dispatchEvent(new f.w.Event('input'));assert.equal(count,3);assert.equal(e._config.future.keep,true);
 }finally{f.close();}});
}
