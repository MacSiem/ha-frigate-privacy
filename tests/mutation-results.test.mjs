import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const initial=()=>({cameras:[{camera_id:'front',name:'Front'}],paused:{},schedules:[],last_operations:{}});
const pauseResult=()=>({ok:true,phase:'paused',results:[{camera_id:'front',paused:true,phase:'paused'}],state:{paused:{front:{phase:'paused'}}}});
const pausedState=()=>({...initial(),paused:{front:{phase:'paused',active:true}}});
for(const path of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']){
 async function fixture(lang='en'){
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'}),w=dom.window;
  w.eval(readFileSync(new URL('../'+path,import.meta.url),'utf8'));
  const c=w.document.createElement('ha-frigate-privacy');c.setConfig({show_support:false});w.document.body.append(c);
  c.hass={language:lang,user:{id:'admin',is_admin:true},connection:{connected:true},states:{},callWS:async()=>initial()};await tick();
  return{c,w,close(){c.remove();w.close();},wire(result,state=initial()){c._hass.callWS=async m=>m.type.endsWith('/get_state')?(state instanceof Error?Promise.reject(state):state):result;}};
 }
 for(const lang of ['en','pl']){
  test(path+': '+lang+' camera contracts and durable localized results',async()=>{
   const f=await fixture(lang);try{
    const cases=[[null,'unconfirmed'],[{},'unconfirmed'],[{ok:true},'unconfirmed'],[{phase:'partial'},'partial'],[{ok:false,phase:'partial'},'partial'],[pauseResult(),'success'],[{...pauseResult(),ok:false},'unconfirmed'],[{...pauseResult(),phase:'active'},'unconfirmed'],[{...pauseResult(),results:[]},'unconfirmed'],[{ok:false,phase:'error'},'error']];
    for(const [result,expected] of cases){f.wire(result,pausedState());assert.equal(await f.c._pause(),expected==='success');assert.equal(f.c._mutationOutcome.code,expected);assert.equal(f.c.shadowRoot.querySelector('[data-action-result] [data-result-state]')?.dataset.resultState,expected);}
    f.wire({...pauseResult(),results:[{camera_id:'front',paused:false,phase:'partial'}]},pausedState());assert.equal(await f.c._pause(),false);assert.equal(f.c._mutationOutcome.code,'partial');
    assert.match(f.c.shadowRoot.querySelector('[data-action-result]').textContent,lang==='pl'?/Częściowo/:/Partial/);
    f.c._applyState({...pausedState(),paused:{front:{phase:'partial',active:true}}});assert.equal(f.c._phaseSummary().label,lang==='pl'?'1 kamera: wynik częściowy':'1 camera: partial result');
    f.c._showToast('', '');f.c.setActiveTab('info');assert.equal(f.c.shadowRoot.querySelector('[data-action-result] [data-result-state]').dataset.resultState,'partial');
    f.wire(pauseResult(),new Error('RAW_PRIVATE_READ_ERROR'));assert.equal(await f.c._pause(),false);assert.equal(f.c._mutationOutcome.code,'unconfirmed');assert.doesNotMatch(f.c.shadowRoot.textContent,/RAW_PRIVATE_READ_ERROR/);
    f.wire(pauseResult(),{paused:{front:{phase:'paused'}}});await f.c._pause();assert.equal(f.c._mutationOutcome.code,'unconfirmed');
    f.wire({ok:false,phase:'error'},new Error('RAW_FAILED_READ'));await f.c._pause();assert.equal(f.c._mutationOutcome.code,'unconfirmed');
    f.wire({phase:'partial'},new Error('RAW_PARTIAL'));await f.c._pause();assert.equal(f.c._mutationOutcome.code,'partial');
    f.c._hass.callWS=async()=>{throw {code:'UNKNOWN_PRIVATE_CODE',message:'RAW_PRIVATE_MUTATION'};};await f.c._pause();assert.equal(f.c._mutationOutcome.code,'unconfirmed');assert.doesNotMatch(f.c.shadowRoot.textContent,/UNKNOWN_PRIVATE_CODE|RAW_PRIVATE_MUTATION/);
    f.c._hass.callWS=async()=>{throw {code:'invalid_payload',message:'RAW_PRIVATE_MUTATION'};};await f.c._pause();assert.equal(f.c._mutationOutcome.code,'error');assert.doesNotMatch(f.c.shadowRoot.textContent,/invalid_payload|RAW_PRIVATE/);
   }finally{f.close();}
  });
  test(path+': '+lang+' schedule confirmation requires matching saved or deleted state',async()=>{
   const f=await fixture(lang);try{
    const schedule={id:'night',label:'Night',enabled:true,days:[1,2],startHour:18,startMin:0,endHour:20,endMin:0,repeat:true};
    const payload={action:'upsert',schedule};
    f.wire({schedule},{...initial(),schedules:[schedule]});assert.equal(await f.c._runMutation('set_schedule',payload),true);
    f.wire({schedule:{...schedule,label:'Other'}},{...initial(),schedules:[{...schedule,label:'Other'}]});assert.equal(await f.c._runMutation('set_schedule',payload),false);
    f.wire({schedule},{...initial(),schedules:[{...schedule,label:'Other'}]});assert.equal(await f.c._runMutation('set_schedule',payload),false);assert.equal(f.c._mutationOutcome.code,'unconfirmed');
    f.wire({},initial());assert.equal(await f.c._runMutation('set_schedule',payload),false);
    f.wire({deleted:true},initial());assert.equal(await f.c._runMutation('set_schedule',{action:'delete',schedule_id:'night'}),true);
    f.wire({deleted:true},{...initial(),schedules:[schedule]});assert.equal(await f.c._runMutation('set_schedule',{action:'delete',schedule_id:'night'}),false);
    f.wire({schedule},new Error('READ_FAILED'));await f.c._runMutation('set_schedule',payload);assert.equal(f.c._mutationOutcome.code,'unconfirmed');
   }finally{f.close();}
  });
 }
 test(path+': resume requires valid per-camera proof and matching readback',async()=>{
  const f=await fixture();try{
   const result={ok:true,phase:'active',results:[{camera_id:'front',resumed:true,phase:'active'}]};f.c._applyState(pausedState());f.wire(result);assert.equal(await f.c._resume(),true);
   f.wire(result);assert.equal(await f.c._resume(),true); // Backend falls back to discovered cameras when no pause is stored.
   f.wire(result,pausedState());assert.equal(await f.c._resume(),false);assert.equal(f.c._mutationOutcome.code,'unconfirmed');
   f.wire({...result,ok:false,phase:'error',results:[result.results[0],{camera_id:'back',resumed:false,phase:'error'}]});await f.c._resume();assert.equal(f.c._mutationOutcome.code,'partial');
  }finally{f.close();}
 });
 test(path+': wire remains blocked across role change; old result cannot restore outcome',async()=>{
  const f=await fixture();try{
   const owner=f.c._hass;let finish;let writes=0;f.c._hass.callWS=m=>m.type.endsWith('/get_state')?Promise.resolve(initial()):(writes++,new Promise(r=>{finish=r;}));
   const pending=f.c._pause();assert.equal(f.c._mutationOutcome.code,'not_checked');
   f.c.hass={...owner,user:{id:'admin',is_admin:false}};assert.equal(f.c._mutationOutcome,null);
   f.c.hass=owner;await tick();assert.equal(await f.c._pause(),false);assert.equal(writes,1);assert.equal(f.c.shadowRoot.querySelector('[data-action="pause-custom"]').disabled,true);
   finish(pauseResult());assert.equal(await pending,false);assert.equal(f.c._mutationOutcome,null);assert.equal(f.c._mutationWire,null);assert.equal(f.c.shadowRoot.querySelector('[data-action="pause-custom"]').disabled,false);
  }finally{f.close();}
 });
}
