import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';

const settle=()=>new Promise(resolve=>setTimeout(resolve,0));
const source=readFileSync(new URL('../ha-frigate-privacy.js',import.meta.url),'utf8');
async function fixture({language='en',notifications,reply}={}) {
  const dom=new JSDOM('<html><body></body></html>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/'});
  const w=dom.window, clock={now:Date.parse('2026-10-16T12:00:00Z')};
  w.Date.now=()=>clock.now;
  const NativeDateTime=w.Intl.DateTimeFormat;
  w.Intl.DateTimeFormat=function(locale,options){return new NativeDateTime(locale,options||{timeZone:'America/New_York'});};
  w.eval(source);
  const c=w.document.createElement('ha-frigate-privacy');c.setConfig({show_support:false});w.document.body.append(c);
  const state={recovery_ready:true,notifications,cameras:[
    {camera_id:'front',entity_id:'camera.front',name:'Front',camera_state:'off',switches:[]},
    {camera_id:'garden',entity_id:'camera.garden',name:'Garden',camera_state:'idle',switches:[]}],
    paused:{front:{active:true,phase:'partial',started_at:'2026-10-16T12:00:00Z',ends_at:'2026-10-16T12:15:00Z',stream_type:'all',target_outcomes:{'switch.front_recordings':'paused'}},
      garden:{active:true,phase:'paused',started_at:'2026-10-16T12:00:00Z',ends_at:'2026-10-16T12:30:00Z',stream_type:'all'}},last_operations:{},schedules:[]};
  const calls=[];
  const hass={language,locale:{language,time_format:'24',time_zone:'local'},config:{time_zone:'Asia/Tokyo'},user:{id:'owner',is_admin:true,is_active:true},connection:{connected:true},states:{},callWS:async message=>{
    calls.push(message);if(message.type.endsWith('/get_state'))return state;
    if(message.type.endsWith('/test_notification'))return reply?reply(message):{status:'ha_accepted'};
    throw Error('Unexpected camera mutation');
  }};
  c.hass=hass;await settle();
  return {c,w,dom,clock,hass,calls,state,close(){c.remove();w.close();}};
}

test('deadline is short in the system zone; full evidence retains time and zone',async()=>{
  const f=await fixture();try {
    const feedback=f.c.shadowRoot.querySelector('[data-camera-feedback="front"]');
    const short=feedback.querySelector('[data-camera-deadline]');
    assert.ok(short,'a short user-facing deadline is required');
    assert.match(short.textContent,/08:15/,'local profile follows browser New York, not server Tokyo');
    assert.doesNotMatch(short.textContent,/2026|GMT|Tokyo|12:15/);
    assert.match(feedback.querySelector('details').textContent,/2026.*08:15|08:15.*2026/);
    assert.match(feedback.querySelector('details').textContent,/America\/New_York/);
    f.hass.locale.time_zone='server';f.hass.locale.time_format='12';f.c.hass=f.hass;
    assert.match(f.c.shadowRoot.querySelector('[data-camera-deadline="front"]').textContent,/09:15.*PM/i);
    assert.equal(f.c._paused.front.ends_at,'2026-10-16T12:15:00Z','display changes retain the absolute server deadline');
  } finally {f.close();}
});

test('timer and progress tick in place, keep controls and await authoritative backend after expiry',async()=>{
  const f=await fixture();try {
    const timer=f.c.shadowRoot.querySelector('[data-camera-countdown="front"]');
    const progress=f.c.shadowRoot.querySelector('[data-camera-progress="front"]');
    assert.ok(progress,'timer has a bounded progress indicator');
    const input=f.c.shadowRoot.querySelector('.input-minutes');input.focus();input.value='73';
    const calls=f.calls.length;
    assert.match(timer.textContent,/15 min/);assert.equal(Number(progress.value),0);
    f.clock.now+=5*60000;f.c._tickCountdowns();
    assert.equal(f.c.shadowRoot.querySelector('[data-camera-progress="front"]'),progress);
    assert.equal(f.c.shadowRoot.querySelector('[data-camera-countdown="front"]'),timer);
    assert.match(timer.textContent,/10 min/);assert.ok(Number(progress.value)>30&&Number(progress.value)<35);
    assert.equal(f.c.shadowRoot.activeElement,input);assert.equal(input.value,'73');assert.equal(f.calls.length,calls);
    f.clock.now+=11*60000;f.c._tickCountdowns();assert.match(timer.textContent,/awaiting.*backend/i);
    assert.equal(Number(progress.value),100);assert.equal(f.c._paused.front.phase,'partial');
  } finally {f.close();}
});

test('partial summary counts affected cameras and focuses the camera without changing selection',async()=>{
  const f=await fixture({language:'pl'});try {
    f.c.setActiveTab('actions');
    const summary=f.c.shadowRoot.querySelector('button[data-camera-summary]');
    assert.ok(summary,'partial header is a keyboard action');
    assert.match(summary.textContent,/1 kamera.*wynik częściowy/i);
    const selected=[...f.c._selectedCameras];summary.click();
    assert.equal(f.c._activeTab,'control');assert.equal(f.c.shadowRoot.activeElement?.dataset.camera,'front');
    assert.deepEqual([...f.c._selectedCameras],selected);
  } finally {f.close();}
});

for(const language of ['en','pl'])test(`notification setup ${language}: saved OFF is explicit and opening never sends`,async()=>{
  const f=await fixture({language,notifications:{destination:'',label:'',available:false,events:{errors:true,paused:false,resumed:false,scheduled:false}}});try {
    f.c.setActiveTab('actions');const block=f.c.shadowRoot.querySelector('[data-notification-setup]');assert.ok(block);
    assert.match(block.textContent,language==='pl'?/Wyłączone|Wyłączony/:/Off/);
    assert.match(block.textContent,language==='pl'?/Konfiguruj/:/Configure/);
    assert.ok(block.querySelector('a[href="/config/integrations/integration/ha_frigate_privacy"]'));
    assert.equal(block.querySelector('[data-notification-test]').disabled,true);
    f.c._updateUI();assert.equal(f.calls.filter(m=>m.type.endsWith('/test_notification')).length,0);
  } finally {f.close();}
});

test('notification test uses saved settings only, single flight and truthful acceptance',async()=>{
  let resolve;
  const f=await fixture({notifications:{destination:'notify.qa',label:'QA <img src=x>',available:true,events:{errors:true,paused:false,resumed:false,scheduled:false}},reply:()=>new Promise(r=>resolve=r)});try {
    f.c.setActiveTab('actions');let block=f.c.shadowRoot.querySelector('[data-notification-setup]');
    assert.ok(block);assert.equal(block.querySelector('img'),null);assert.match(block.textContent,/QA <img src=x>/);
    const button=block.querySelector('[data-notification-test]');button.click();button.click();await settle();
    const sends=f.calls.filter(m=>m.type.endsWith('/test_notification'));assert.equal(sends.length,1);
    assert.deepEqual(Object.keys(sends[0]),['type'],'browser cannot supply a recipient, body or camera');
    assert.equal(f.c.shadowRoot.querySelector('[data-notification-test]').disabled,true);
    resolve({status:'ha_accepted'});await settle();
    const result=f.c.shadowRoot.querySelector('[data-notification-result]');assert.equal(result.getAttribute('role'),'status');
    assert.match(result.textContent,/Home Assistant accepted/);assert.match(result.textContent,/does not confirm delivery/i);
    assert.equal(f.calls.filter(m=>!m.type.endsWith('/get_state')&&!m.type.endsWith('/test_notification')).length,0);
  } finally {f.close();}
});

test('notification state and late test outcome disappear on identity change',async()=>{
  let resolve;
  const f=await fixture({notifications:{destination:'notify.private',label:'Private destination',available:true,events:{errors:true}},reply:()=>new Promise(r=>resolve=r)});try {
    f.c.setActiveTab('actions');const button=f.c.shadowRoot.querySelector('[data-notification-test]');assert.ok(button);button.click();await settle();
    f.c.hass={...f.hass,user:{id:'household',is_admin:false,is_active:true}};
    resolve({status:'ha_accepted'});await settle();
    assert.doesNotMatch(f.c.shadowRoot.textContent,/Private destination|Home Assistant accepted/);
    assert.equal(f.c.shadowRoot.querySelector('[data-notification-setup]'),null);
  } finally {f.close();}
});

test('unavailable and missing snapshots do not claim notification delivery or enable a test',async()=>{
  for(const notifications of [undefined,{destination:'notify.missing',label:'Missing phone',available:false,events:{errors:true}}]) {
    const f=await fixture({notifications});try {
      f.c.setActiveTab('actions');const block=f.c.shadowRoot.querySelector('[data-notification-setup]');assert.ok(block);
      assert.equal(block.querySelector('[data-notification-test]').disabled,true);
      assert.match(block.textContent,notifications?/unavailable/i:/unconfirmed|refresh/i);
      assert.equal(f.calls.filter(m=>m.type.endsWith('/test_notification')).length,0);
    } finally {f.close();}
  }
});

test('ordinary hass updates retain pending test acceptance; timeout is unconfirmed without retry',async()=>{
  let resolve,timeout;
  const f=await fixture({notifications:{destination:'notify.qa',label:'QA',available:true,events:{errors:true}},reply:()=>new Promise(r=>resolve=r)});try {
    f.c.setActiveTab('actions');
    const button=f.c.shadowRoot.querySelector('[data-notification-test]');assert.ok(button);
    const originalTimeout=f.w.setTimeout;
    f.w.setTimeout=(callback,ms,...args)=>ms===15000?(timeout=callback,999):originalTimeout(callback,ms,...args);
    button.click();await settle();
    f.c.hass={...f.hass};resolve({status:'ha_accepted'});await settle();
    assert.match(f.c.shadowRoot.querySelector('[data-notification-result]').textContent,/Home Assistant accepted/);
    f.c.shadowRoot.querySelector('[data-notification-test]').click();await settle();timeout();
    assert.match(f.c.shadowRoot.querySelector('[data-notification-result]').textContent,/unconfirmed/i);
    assert.equal(f.c.shadowRoot.querySelector('[data-notification-test]').disabled,true);
    resolve({status:'ha_accepted'});await settle();
    assert.match(f.c.shadowRoot.querySelector('[data-notification-result]').textContent,/unconfirmed/i);
    assert.equal(f.calls.filter(m=>m.type.endsWith('/test_notification')).length,2,'one request for each explicit click; timeout never retries');
  } finally {f.close();}
});

test('camera names use one natural locale order without changing selected IDs',async()=>{
  const f=await fixture({language:'pl'});try {
    f.state.cameras[0].name='Kamera 10';f.state.cameras[1].name='Kamera 2';f.c._selectedCameras.add('front');f.c._applyState(f.state);
    const rows=[...f.c.shadowRoot.querySelectorAll('[data-camera]')].filter(e=>e.dataset.camera!=='__all__');
    assert.deepEqual(rows.map(e=>e.querySelector('.camera-name').textContent),['Kamera 2','Kamera 10']);
    assert.deepEqual([...f.c._selectedCameras],['front']);
  } finally {f.close();}
});

test('history distinguishes repeated local DST times and profile formatting does not fetch again',async()=>{
  const f=await fixture();try {
    const count=f.calls.length;
    const first='2026-11-01T05:30:00Z',second='2026-11-01T06:30:00Z';
    assert.notEqual(f.c._periodTime(first),f.c._periodTime(second),'two actual instants must not share an ambiguous local label');
    assert.match(f.c._periodTime(first),/GMT-4/);
    assert.match(f.c._periodTime(second),/GMT-5/);
    f.hass.locale.time_format='12';f.c.hass=f.hass;
    assert.match(f.c._periodTime(first),/01:30.*AM/i);
    assert.equal(f.calls.length,count,'format-only updates do not request data');
    f.c.setActiveTab('schedule');
    assert.match(f.c.shadowRoot.querySelector('[data-schedule-zone]')?.textContent||'',/Asia\/Tokyo/);
    assert.equal(f.c.shadowRoot.querySelector('.input-start').value,'18:00','display zone does not reinterpret operational schedule hours');
  }finally{f.close();}
});
