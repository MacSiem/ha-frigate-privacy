import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
for(const sourcePath of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']){
 async function fixture(){
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window;
  class Picture extends w.HTMLElement{setConfig(config){this.config=config;}set hass(value){this.value=value;}disconnectedCallback(){this.detached=(this.detached||0)+1;}}
  w.customElements.define('hui-picture-entity-card',Picture);
  w.loadCardHelpers=async()=>({createCardElement:()=>w.document.createElement('hui-picture-entity-card')});
  w.eval(readFileSync(new URL('../'+sourcePath,import.meta.url),'utf8'));
  const c=w.document.createElement('ha-frigate-privacy');c.setConfig({show_support:false});w.document.body.append(c);
  const state={cameras:[{camera_id:'front',entity_id:'camera.front',name:'Front',switches:[]}],paused:{},last_operations:{},schedules:[],recovery_ready:true};
  const calls=[];const hass={language:'en',user:{id:'owner',is_admin:true},connection:{connected:true},config:{time_zone:'UTC'},states:{},callWS:async msg=>{calls.push(msg);return state;}};
  c.hass=hass;await tick();c.shadowRoot.querySelector('[data-preview-camera]').click();await tick();
  return {w,c,state,calls,r:c.shadowRoot,close(){c.remove();w.close();}};
 }
 for(const change of ['camera','scope','duration'])test(sourcePath+': '+change+' keeps mounted controls, focus and running preview',async()=>{
  const f=await fixture();try{
   const camera=f.r.querySelector('[data-camera="front"]'),scope=f.r.querySelector('[data-scope="sub"]'),input=f.r.querySelector('.input-minutes'),preview=f.r.querySelector('hui-picture-entity-card');
   assert.ok(preview?.isConnected);const target=change==='camera'?camera:change==='scope'?scope:input;target.focus();
   if(change==='duration'){input.value='73';input.dispatchEvent(new f.w.Event('change'));}else target.click();
   assert.equal(f.r.querySelector('[data-camera="front"]'),camera,'selecting a draft must retain the mounted camera node');
   assert.equal(f.r.querySelector('.input-minutes'),input,'draft input stays mounted');
   assert.equal(f.r.activeElement,target,'focus stays on the same node');
   assert.equal(preview.detached||0,0,'running media must never disconnect during draft updates');
   assert.equal(f.r.querySelector('hui-picture-entity-card'),preview);
   if(change==='camera')assert.equal(camera.getAttribute('aria-pressed'),'true');
   if(change==='scope')assert.equal(scope.getAttribute('aria-checked'),'true');
   if(change==='duration')assert.equal(input.value,'73');
   assert.equal(f.calls.filter(msg=>!msg.type.endsWith('/get_state')).length,0,'draft changes cannot control cameras');
  }finally{f.close();}
 });
}
