import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';

const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
for(const path of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']){
 async function fixture({method='_getRoutes',lazy=false,reject=false,held=false}={}){
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window;
  const made=[],loads=[];let complete;
  class Picture extends w.HTMLElement {
   setConfig(config){this.previewConfig=config;}
   set hass(value){assert.ok(this.previewConfig,'configuration precedes hass');this.realHass=value;}
  }
  const define=()=>{if(!w.customElements.get('hui-picture-entity-card'))w.customElements.define('hui-picture-entity-card',Picture);};
  if(!lazy)define();
  const helpers={createCardElement(config){const node=w.document.createElement('hui-picture-entity-card');made.push(node);if(node.setConfig)node.setConfig(config);else w.customElements.whenDefined(node.localName).then(()=>{w.customElements.upgrade(node);node.setConfig(config);});return node;}};
  class Resolver extends w.HTMLElement{}
  Resolver.prototype[method]=function(panels){assert.equal(this.isConnected,false);const name=panels[0].url_path;return {routes:{[name]:{load:async()=>{loads.push(name);if(held)await new Promise(resolve=>{complete=resolve;});if(reject)throw Error('PRIVATE_LOADER_ERROR');w.loadCardHelpers=async()=>helpers;}}}};};
  w.customElements.define('partial-panel-resolver',Resolver);
  w.eval(readFileSync(new URL('../'+path,import.meta.url),'utf8'));
  const c=w.document.createElement('ha-frigate-privacy');c.setConfig({show_support:false});w.document.body.append(c);
  const state={cameras:[{camera_id:'front',entity_id:'camera.front',name:'Front',switches:[]}],paused:{},last_operations:{},schedules:[]};
  const hass={language:'en',user:{id:'admin',is_admin:true},connection:{connected:true},config:{time_zone:'UTC'},states:{},callWS:async()=>state};c.hass=hass;await tick();
  return {c,w,made,loads,hass,define,release:()=>complete(),open:()=>c.shadowRoot.querySelector('[data-preview-camera]').click(),close(){c.remove();w.close();}};
 }
 for(const method of ['_getRoutes','getRoutes'])test(path+': standalone preview bootstraps native route via '+method,async()=>{
  const f=await fixture({method});try{assert.equal(f.loads.length,0);f.open();await tick();assert.equal(f.loads.length,1);assert.equal(f.made.length,1);assert.equal(f.made[0].isConnected,true);assert.equal(f.made[0].previewConfig.entity,'camera.front');assert.equal(f.made[0].realHass,f.hass);assert.equal(f.w.location.pathname,'/');assert.equal(f.w.document.querySelector('partial-panel-resolver'),null);}finally{f.close();}
 });
 test(path+': lazy native card is upgraded before hass and mount',async()=>{
  const f=await fixture({lazy:true});try{f.open();await tick();assert.equal(f.made.length,1);const node=f.made[0];assert.equal(node.isConnected,false);assert.equal(Object.hasOwn(node,'hass'),false);f.define();await tick();assert.equal(node.isConnected,true);assert.equal(node.realHass,f.hass);assert.equal(Object.hasOwn(node,'hass'),false);}finally{f.close();}
 });
 test(path+': bootstrap settling after close or role change never creates media',async()=>{
  for(const revoke of ['close','role']){const f=await fixture({held:true});try{f.open();await tick();assert.equal(f.loads.length,1);if(revoke==='close')f.open();else f.c.hass={...f.hass,user:{id:'household',is_admin:false}};f.release();await tick();assert.equal(f.made.length,0);assert.equal(f.c.shadowRoot.querySelector('[data-preview-host]'),null);}finally{f.close();}}
 });
 test(path+': rejected bootstrap is explicit, redacted and only retries on user action',async()=>{
  const f=await fixture({reject:true});try{f.open();await tick();assert.equal(f.loads.length,1);assert.match(f.c.shadowRoot.querySelector('[data-preview-host]').textContent,/unavailable/);assert.doesNotMatch(f.c.shadowRoot.textContent,/PRIVATE_LOADER_ERROR/);f.c.hass=f.hass;await tick();assert.equal(f.loads.length,1);f.open();f.open();await tick();assert.equal(f.loads.length,2);}finally{f.close();}
 });
 test(path+': closing during lazy card import prevents a late mount',async()=>{
  const f=await fixture({lazy:true});try{f.open();await tick();assert.equal(f.made.length,1);f.open();f.define();await tick();assert.equal(f.made[0].isConnected,false);assert.equal(f.made[0].realHass,undefined);}finally{f.close();}
 });
 test(path+': unsupported resolver and stalled import produce a bounded failure',async()=>{
  for(const stalled of [false,true]){const f=await fixture({method:'unsupported',held:stalled});try{
   if(stalled){const resolver=f.w.customElements.get('partial-panel-resolver');resolver.prototype._getRoutes=resolver.prototype.unsupported;}
   const schedule=f.w.setTimeout.bind(f.w);f.w.setTimeout=(callback,ms,...args)=>schedule(callback,ms===10000?0:ms,...args);
   f.open();await tick();await tick();await tick();assert.match(f.c.shadowRoot.querySelector('[data-preview-host]').textContent,/unavailable/);assert.equal(f.made.length,0);
   if(stalled){f.release();await tick();assert.equal(f.made.length,0);}
  }finally{f.close();}}
 });
}
