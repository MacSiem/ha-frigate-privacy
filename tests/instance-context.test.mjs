import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const settle = () => new Promise(resolve => setTimeout(resolve, 0));
const state = name => ({ cameras: [{camera_id:name, name, entity_id:`camera.${name}`}], schedules:[], paused:{}, last_operations:{}, recovery_ready:true });
for (const file of ['ha-frigate-privacy.js','custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js']) {
  function fixture() {
    const dom = new JSDOM('<html><body></body></html>', {runScripts:'dangerously', pretendToBeVisual:true, url:'http://localhost/'});
    dom.window.eval(readFileSync(new URL('../'+file, import.meta.url), 'utf8'));
    const card = dom.window.document.createElement('ha-frigate-privacy');
    const pending = [], calls = [];
    let current = state('old_home');
    const hass = {states:{},themes:{darkMode:false},language:'en',config:{instance_id:'home-a',time_zone:'UTC'},user:{id:'admin',is_admin:true,is_active:true},connection:{connected:true},callWS:message => {
      calls.push(message);
      if (message.type.endsWith('/get_periods')) return new Promise(resolve => pending.push(resolve));
      return Promise.resolve(current);
    }};
    card.setConfig({type:'custom:ha-frigate-privacy'}); card.hass=hass; dom.window.document.body.append(card);
    return {dom,card,hass,pending,calls,setState:value => {current=value;}};
  }
  test(file+': same object instance change clears cached private state before fresh read', async () => {
    const f=fixture(); try {
      await settle(); assert.equal(f.card._cameras[0].camera_id,'old_home');
      f.setState(state('new_home'));
      f.hass.config.instance_id='home-b'; f.card.hass=f.hass;
      assert.equal(f.card._cameras.length,0,'old household cameras must disappear synchronously');
      await settle(); assert.equal(f.card._cameras[0].camera_id,'new_home');
    } finally {f.dom.window.close();}
  });
  test(file+': pending history from another instance is discarded without automatic history retry', async () => {
    const f=fixture(); try {
      await settle(); f.card.setActiveTab('history');
      const pending=f.card._refreshPeriods();
      f.hass.config.instance_id='home-b'; f.card.hass=f.hass;
      f.pending[0]({schema:1,status:'ready',durability:'confirmed',retention:{max_periods:200,max_days:30,read_filtered:true},periods:[]});
      await pending;
      assert.equal(f.card._periodInfo,null,'even an empty old response must not become new-instance evidence');
      assert.equal(f.calls.filter(c=>c.type.endsWith('/get_periods')).length,1);
    } finally {f.dom.window.close();}
  });
  test(file+': in-place active-account revocation clears private camera state', async () => {
    const f=fixture(); try {
      await settle(); f.hass.user.is_active=false; f.card.hass=f.hass;
      assert.equal(f.card._cameras.length,0);
      assert.doesNotMatch(f.card.shadowRoot.textContent,/old_home/);
    } finally {f.dom.window.close();}
  });
  test(file+': ordinary same-session update preserves cached state and does not refetch', async () => {
    const f=fixture(); try {
      await settle(); const count=f.calls.length;
      f.card.hass={...f.hass,states:{'sensor.tick':{state:'1'}}};
      assert.equal(f.card._cameras[0].camera_id,'old_home');
      assert.equal(f.calls.length,count);
    } finally {f.dom.window.close();}
  });
}
