import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const tick=()=>new Promise(r=>setTimeout(r,0));
for(const source of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']){
 async function fixture(width=900){
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window,observers=[];
  w.ResizeObserver=class{constructor(fn){this.fn=fn;observers.push(this);}observe(){}disconnect(){this.closed=true;}};
  class Picture extends w.HTMLElement{setConfig(){}set hass(value){}disconnectedCallback(){this.detached=(this.detached||0)+1;}}
  w.customElements.define('hui-picture-entity-card',Picture);w.loadCardHelpers=async()=>({createCardElement:()=>w.document.createElement('hui-picture-entity-card')});
  w.eval(readFileSync(new URL('../'+source,import.meta.url),'utf8'));
  const c=w.document.createElement('ha-frigate-privacy');c.getBoundingClientRect=()=>({width});c.setConfig({show_support:false});w.document.body.append(c);
  const calls=[],state={cameras:[{camera_id:'front',entity_id:'camera.front',name:'Front',switches:[]}],paused:{},last_operations:{},schedules:[],recovery_ready:true};
  const hass={language:'en',user:{id:'owner',is_admin:true},connection:{connected:true},config:{time_zone:'UTC'},states:{},callWS:async msg=>{calls.push(msg);if(!msg.type.endsWith('/get_state'))throw Error('Unexpected mutation');return state;}};
  c.hass=hass;await tick();await tick();
  return{w,c,r:c.shadowRoot,hass,calls,async resize(n){width=n;observers.filter(o=>!o.closed).forEach(o=>o.fn());await tick();},async preview(){c.shadowRoot.querySelector('[data-preview-camera]').click();await tick();return c.shadowRoot.querySelector('hui-picture-entity-card');},close(){c.remove();w.close();}};
 }
 test(source+': default help reacts to wide/narrow card resize without replacing focused draft or media',async()=>{
  const f=await fixture();try{
   const media=await f.preview(),help=f.r.querySelector('[data-intro]'),input=f.r.querySelector('.input-minutes');assert.ok(help.open);assert.ok(media?.isConnected);input.focus();input.value='73';input.dispatchEvent(new f.w.Event('change'));
   await f.resize(390);assert.equal(help.open,false,'default wide help must collapse when the actual card becomes narrow');
   assert.equal(f.r.querySelector('.input-minutes'),input);assert.equal(f.r.activeElement,input);assert.equal(input.value,'73');assert.equal(f.r.querySelector('hui-picture-entity-card'),media);assert.equal(media.detached||0,0);
   f.c.hass=f.hass;await tick();assert.equal(f.r.querySelector('.input-minutes'),input);assert.equal(f.r.querySelector('hui-picture-entity-card'),media);
   await f.resize(900);assert.equal(f.r.querySelector('[data-intro]').open,true,'automatic collapse must not be stored as a user dismissal');
   assert.equal(f.calls.filter(m=>!m.type.endsWith('/get_state')).length,0);
  }finally{f.close();}
 });
 test(source+': fresh narrow help stays closed but explicit opening survives normal refresh and resize',async()=>{
  const f=await fixture(390);try{
   const help=f.r.querySelector('[data-intro]');assert.equal(help.open,false);help.querySelector('summary').click();await tick();assert.equal(help.open,true);
   f.c.hass=f.hass;await tick();assert.equal(f.r.querySelector('[data-intro]').open,true,'a deliberate open must not be undone by state refresh');
   await f.resize(900);await f.resize(390);assert.equal(f.r.querySelector('[data-intro]').open,true);
  }finally{f.close();}
 });
 test(source+': deliberate closure remains closed after resize and remount for the same user',async()=>{
  const f=await fixture();try{
   f.r.querySelector('[data-intro] summary').click();await tick();assert.equal(f.r.querySelector('[data-intro]').open,false);
   await f.resize(390);await f.resize(900);assert.equal(f.r.querySelector('[data-intro]').open,false);
   f.c.remove();f.w.document.body.append(f.c);await tick();assert.equal(f.r.querySelector('[data-intro]').open,false);
  }finally{f.close();}
 });
}
