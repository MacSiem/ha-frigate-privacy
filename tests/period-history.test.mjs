import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
const source = readFileSync(new URL('../ha-frigate-privacy.js',import.meta.url),'utf8');
const settle = () => new Promise(resolve => setTimeout(resolve,0));
function fixture() {
  const dom = new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'});
  dom.window.eval(source);
  const card = dom.window.document.createElement('ha-frigate-privacy');
  const listeners = new Map();
  const connection = {connected:true,addEventListener(type,cb){listeners.set(type,cb);},removeEventListener(type,cb){if(listeners.get(type)===cb)listeners.delete(type);}};
  let resolveHistory; const calls = [];
  const callWS = message => {calls.push(message); if(message.type.endsWith('/get_periods')) return new Promise(resolve => {resolveHistory=resolve;});return Promise.resolve({cameras:[],schedules:[],paused:{},last_operations:{},recovery_ready:true});};
  const hass = {states:{},themes:{darkMode:false},language:'en',config:{time_zone:'Europe/Warsaw'},user:{id:'admin',is_admin:true,is_active:true,groups:[{id:'system-admin'}]},connection,callWS};
  card.setConfig({type:'custom:ha-frigate-privacy',unknown_field:'preserved'});card.hass=hass;
  dom.window.document.body.append(card);
  return {dom,card,hass,calls,listeners,resolve(value){resolveHistory(value);}};
}
function row(index=0) {return {id:String(index).padStart(64,'0'),camera_id:'front',generation:index,started_at:'2026-10-12T18:00:00Z',ended_at:null,planned_ends_at:null,observed_at:null,phase:'partial',source:'manual',reason:'pause_incomplete',end_reason:null,verified_restore:false,duration_seconds:null,channels:[{channel:'detection',target:'switch.front_detect',pause_outcome:'paused',restore_outcome:'unknown',observed_state:'unknown'}],unknown_channels:[],evidence_scope:'transition_intent'};}
function response(count=1){return {schema:1,status:'ready',durability:'confirmed',retention:{max_periods:200,max_days:30,read_filtered:true},periods:Array.from({length:count},(_,i)=>row(i))};}
{
  const f=fixture();await settle();
  assert.equal(f.calls.filter(c=>c.type.endsWith('/get_periods')).length,0,'mount does not request history');
  f.card.setActiveTab('history');await settle();
  assert.equal(f.calls.filter(c=>c.type.endsWith('/get_periods')).length,0,'opening history does not request history');
  const pending=f.card._refreshPeriods();f.card._refreshPeriods();
  assert.equal(f.calls.filter(c=>c.type.endsWith('/get_periods')).length,1);
  f.resolve(response(120));await pending;
  assert.equal(f.card.shadowRoot.querySelectorAll('[data-period-select]').length,50);
  const timelineIds=[...f.card.shadowRoot.querySelectorAll('[data-period-select]')].map(el=>el.dataset.periodSelect);
  f.card.shadowRoot.querySelector('[data-period-view="data"]').click();
  const dataIds=[...f.card.shadowRoot.querySelectorAll('[data-period-select]')].map(el=>el.dataset.periodSelect);
  assert.deepEqual(dataIds,timelineIds,'Timeline and Data use identical validated rows');
  f.card.shadowRoot.querySelector('[data-period-page="next"]').click();
  assert.equal(f.card.shadowRoot.querySelectorAll('[data-period-select]').length,50);
  f.card.shadowRoot.querySelector('[data-period-page="next"]').click();
  assert.equal(f.card.shadowRoot.querySelectorAll('[data-period-select]').length,20);
  assert.match(f.card.shadowRoot.textContent,/UTC/);assert.match(f.card.shadowRoot.textContent,/Europe\/Warsaw/);
  assert.equal(f.card._config.unknown_field,'preserved');f.dom.window.close();
}
for (const change of ['role','active','groups','config','range','language','offline','disconnect','callWS','unmount']) {
  const f=fixture();await settle();f.card.setActiveTab('history');
  const pending=f.card._refreshPeriods();
  if(change==='role')f.card.hass={...f.hass,user:{...f.hass.user,is_admin:false}};
  if(change==='active')f.card.hass={...f.hass,user:{...f.hass.user,is_active:false}};
  if(change==='groups')f.card.hass={...f.hass,user:{...f.hass.user,groups:[]}};
  if(change==='config')f.card.setConfig({...f.card._config,title:'new'});
  if(change==='range')f.card._setPeriodRange(7);
  if(change==='language')f.card.hass={...f.hass,language:'pl'};
  if(change==='offline')f.dom.window.dispatchEvent(new f.dom.window.Event('offline'));
  if(change==='disconnect')f.listeners.get('disconnected')?.();
  if(change==='callWS')f.card.hass={...f.hass,callWS:()=>Promise.resolve({})};
  if(change==='unmount')f.card.remove();
  f.resolve(response());await pending;
  assert.equal(f.card._periods.length,0,`${change}: late private outcome discarded`);
  assert.doesNotMatch(f.card.shadowRoot.textContent,/switch.front_detect/);
  f.dom.window.close();
}
{
  const f=fixture();await settle();f.card.setActiveTab('history');
  const pending=f.card._refreshPeriods();f.card._periodDeadlineExpired();
  await f.card._refreshPeriods();
  assert.equal(f.calls.filter(c=>c.type.endsWith('/get_periods')).length,1,'deadline does not release occupied wire');
  f.resolve(response());await pending;assert.equal(f.card._periods.length,0);
  f.dom.window.close();
}
{
  const f=fixture();await settle();f.card.setActiveTab('history');
  const pending=f.card._refreshPeriods();f.resolve({...response(),periods:[{...row(),started_at:'https://private.invalid',reason:'raw secret error'}]});await pending;
  assert.equal(f.card._periods.length,0,'invalid rows reject the projection');
  assert.doesNotMatch(f.card.shadowRoot.textContent,/private.invalid|raw secret error/);
  f.dom.window.close();
}
{
  const f=fixture();await settle();assert.ok(f.listeners.has('disconnected'),'hass-before-mount binds typed events');
  f.listeners.get('disconnected')();f.listeners.get('ready')();
  assert.equal(f.calls.filter(c=>c.type.endsWith('/get_periods')).length,0,'ready does not retry history');
  f.card.remove();assert.equal(f.listeners.size,0);f.dom.window.close();
}
{
  const f=fixture();await settle();f.card.setActiveTab('history');
  const pending=f.card._refreshPeriods();f.resolve(response());await pending;
  // JSDOM does not cascade shadow styles. Feed the actual rendered stylesheet
  // and actual panel into its light-DOM CSS engine; visual layout remains QA.
  const css=f.dom.window.document.createElement('style');
  css.textContent=[...f.card.shadowRoot.querySelectorAll('style')].map(el=>el.textContent).join('\n');
  f.dom.window.document.head.append(css);
  const rendered=f.card.shadowRoot.querySelector('.history-panel').cloneNode(true);
  f.dom.window.document.body.append(rendered);
  for(const control of rendered.querySelectorAll('button,select')) {
    const style=f.dom.window.getComputedStyle(control);
    assert.ok(Number.parseFloat(style.minHeight)>=44,'history controls preserve 44px touch height');
  }
  f.dom.window.close();
}

for (const change of ['role','groups','config','range','offline','connected_flag','unmount']) {
  const f=fixture();await settle();f.card.setActiveTab('history');
  const pending=f.card._refreshPeriods();f.resolve(response());await pending;
  assert.match(f.card.shadowRoot.textContent,/switch.front_detect/);
  const reads=f.calls.filter(c=>c.type.endsWith('/get_periods')).length;
  if(change==='role')f.card.hass={...f.hass,user:{...f.hass.user,is_admin:false}};
  if(change==='groups')f.card.hass={...f.hass,user:{...f.hass.user,groups:[]}};
  if(change==='config')f.card.setConfig({...f.card._config,title:'Changed scope'});
  if(change==='range')f.card._setPeriodRange(7);
  if(change==='offline')f.dom.window.dispatchEvent(new f.dom.window.Event('offline'));
  if(change==='connected_flag'){f.hass.connection.connected=false;f.card.hass=f.hass;}
  if(change==='unmount')f.card.remove();
  assert.equal(f.card._periods.length,0,`${change}: cached private rows cleared immediately`);
  assert.doesNotMatch(f.card.shadowRoot.textContent,/switch.front_detect/);
  assert.equal(f.calls.filter(c=>c.type.endsWith('/get_periods')).length,reads);
  f.dom.window.close();
}
{
  const f=fixture();await settle();f.card.hass={...f.hass,language:'pl',themes:{darkMode:true}};await settle();
  f.card.setActiveTab('history');const pending=f.card._refreshPeriods();f.resolve(response());await pending;
  assert.match(f.card.shadowRoot.textContent,/Historia okresów/);
  assert.match(f.card.shadowRoot.textContent,/Brak dowodu przywrócenia/);
  assert.ok(f.card.classList.contains('bento-dark'));f.dom.window.close();
}
{
  const f=fixture();await settle();f.card.setActiveTab('history');
  const pending=f.card._refreshPeriods();f.resolve({...response(0),status:'corrupt'});await pending;
  assert.match(f.card.shadowRoot.textContent,/Corrupt format/);
  assert.doesNotMatch(f.card.shadowRoot.textContent,/No recorded periods|No readable periods/,'corruption must not claim measured absence');
  f.dom.window.close();
}
{
  const f=fixture();await settle();f.card.setActiveTab('history');
  const pending=f.card._refreshPeriods();f.resolve(response());await pending;
  f.card._callIntegration=async()=>{throw new Error('synthetic transport failure');};
  await f.card._connectIntegration();
  assert.equal(f.card._periods.length,0,'integration unavailable clears history snapshot');
  assert.doesNotMatch(f.card.shadowRoot.textContent,/switch.front_detect/);
  f.dom.window.close();
}
{
  const f=fixture();await settle();f.card.setActiveTab('history');
  const pending=f.card._refreshPeriods();
  f.card._applyState({paused:{front:{phase:'paused',active:true,generation:1}},last_operations:{},cameras:[],schedules:[]});
  f.resolve(response());await pending;
  assert.equal(f.card._periods.length,0,'a changed producer state discards an older pending history read');
  assert.equal(f.calls.filter(c=>c.type.endsWith('/get_periods')).length,1,'producer changes do not query history automatically');
  f.dom.window.close();
}

{
 const f=fixture();await settle();f.card.setActiveTab('history');const job=f.card._refreshPeriods();f.resolve(response());await job;
 f.card.hass={...f.hass,user:{...f.hass.user,group_ids:['changed-group']}};
 assert.equal(f.card._periods.length,0,'actual group_ids revokes cached history');
 f.dom.window.close();
}
{
 const f=fixture();await settle();f.card.setActiveTab('history');const job=f.card._refreshPeriods();f.resolve(response(51));await job;
 const next=f.card.shadowRoot.querySelector('[data-period-page="next"]');next.focus();next.click();
 assert.ok(f.card.shadowRoot.activeElement && !f.card.shadowRoot.activeElement.disabled,'last page retains a usable keyboard focus');
 f.dom.window.close();
}
{
 const f=fixture();await settle();f.card.setActiveTab('history');const job=f.card._refreshPeriods();
 f.resolve({...response(),periods:[{...row(),phase:'active',ended_at:'2026-10-12T19:00:00Z',duration_seconds:3600,end_reason:'admin_request',verified_restore:true,channels:[]}]});await job;
 assert.equal(f.card._periods.length,0,'a positive flag without any target proof is invalid');
 f.dom.window.close();
}
