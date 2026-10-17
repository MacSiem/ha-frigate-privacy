"""New entity actions, availability, discovery and unload with synthetic HA only."""
import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest
from test_restart_recovery import control, _Hass, _State

PKG = Path(__file__).resolve().parents[1] / 'custom_components/ha_frigate_privacy'


@pytest.fixture
def entities(monkeypatch):
    class Entity:
        def __init__(self):
            pass
        def async_on_remove(self, unsub):
            self.removers.append(unsub)
        def async_schedule_update_ha_state(self, force=False):
            self.updates.append(force)
    for modname, clsname in [('homeassistant.helpers.entity', 'Entity'),
                            ('homeassistant.components.switch', 'SwitchEntity'),
                            ('homeassistant.components.button', 'ButtonEntity'),
                            ('homeassistant.components.sensor', 'SensorEntity')]:
        module = types.ModuleType(modname)
        setattr(module, clsname, Entity if clsname == 'Entity' else type(clsname, (Entity,), {}))
        if clsname == 'SensorEntity':
            module.SensorDeviceClass = types.SimpleNamespace(TIMESTAMP='timestamp', ENUM='enum')
        monkeypatch.setitem(sys.modules, modname, module)
    core = types.ModuleType('homeassistant.core')
    core.callback = lambda fn: fn
    monkeypatch.setitem(sys.modules, 'homeassistant.core', core)
    const = types.ModuleType('homeassistant.const')
    const.EVENT_STATE_CHANGED = 'state_changed'
    monkeypatch.setitem(sys.modules, 'homeassistant.const', const)
    package = types.ModuleType('entity_contract'); package.__path__ = [str(PKG)]
    monkeypatch.setitem(sys.modules, 'entity_contract', package)
    monkeypatch.setitem(sys.modules, 'entity_contract.control', control)
    result = {}
    for name in ('const', 'entity', 'switch', 'button', 'sensor'):
        spec = importlib.util.spec_from_file_location('entity_contract.'+name, PKG/(name+'.py'))
        mod = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, mod)
        spec.loader.exec_module(mod)
        result[name] = mod
    return types.SimpleNamespace(**result)


class Bus:
    def __init__(self):
        self.listeners = []
    def async_listen(self, event, cb):
        item = (event, cb); self.listeners.append(item)
        def remove():
            self.listeners.remove(item)
        return remove
    def fire(self, event, data):
        for kind, cb in list(self.listeners):
            if kind == event:
                cb(types.SimpleNamespace(data=data))


class Storage:
    record = None
    async def async_get_paused(self, camera, **kwargs):
        return {} if camera is None else self.record
    async def async_get_state(self):
        return {'last_outcome':getattr(self, 'outcome', None)}


def prepare(entity, hass):
    entity.hass = hass
    entity._context = types.SimpleNamespace(user_id='member')
    entity.removers = []
    entity.updates = []
    return entity


def test_entity_actions_propagate_caller_context_to_guarded_services(entities):
    async def scenario():
        calls = []
        async def call(*args, **kwargs):
            calls.append((args, kwargs))
        hass = types.SimpleNamespace(services=types.SimpleNamespace(async_call=call))
        storage = Storage()
        switch = prepare(entities.switch.FrigatePrivacySwitch(storage, 'front', 'Front', 'privacy'), hass)
        await switch.async_turn_on()
        await switch.async_turn_off()
        for minutes in (15, 30, 60):
            button = prepare(entities.button.FrigatePrivacyTimerButton(storage, 'front', 'Front', minutes), hass)
            await button.async_press()
            assert calls[-1][0] == ('ha_frigate_privacy', 'pause_camera', {'camera':'front', 'duration_minutes':minutes})
            assert calls[-1][1]['context'] is button._context
        assert calls[0][0] == ('ha_frigate_privacy', 'pause_camera', {'camera':'front'})
        assert calls[1][0][1] == 'resume_camera'
        assert calls[0][1]['context'] is switch._context
        assert all(kwargs['blocking'] for _, kwargs in calls)
    asyncio.run(scenario())


def test_truthful_state_deadline_and_availability(entities):
    async def scenario():
        hass = _Hass(); hass.bus = Bus()
        hass.data = {'ha_frigate_privacy':{'recovery_ready':False}}
        storage = Storage()
        switch = prepare(entities.switch.FrigatePrivacySwitch(storage, 'front', 'Front', 'privacy'), hass)
        deadline = prepare(entities.sensor.FrigatePrivacyDeadline(storage, 'front', 'Front', 'privacy_until'), hass)
        assert not switch.available
        hass.data['ha_frigate_privacy']['recovery_ready'] = True
        assert switch.available
        await switch.async_added_to_hass()
        assert switch.is_on is False
        for phase, expected in [('paused',True), ('partial',None), ('error',None), ('pausing',None)]:
            storage.record = {'phase':phase, 'active':True, 'ends_at':'2030-01-01T12:00:00+00:00'}
            await switch.async_update(); await deadline.async_update()
            assert switch.is_on is expected
            assert deadline.native_value == datetime(2030,1,1,12,tzinfo=timezone.utc)
        storage.record = {'active':False, 'ends_at':'2030-01-01T12:00:00+00:00'}
        await deadline.async_update()
        assert deadline.native_value is None
        for value in [None, 'broken', '2030-01-01T12:00:00']:
            storage.record = {'active':True, 'ends_at':value}
            await deadline.async_update()
            assert deadline.native_value is None
        for state in hass.states.values.values(): state.state = 'unavailable'
        assert not switch.available
        for remove in switch.removers: remove()
        assert not hass.bus.listeners
    asyncio.run(scenario())


def test_late_discovery_deduplicates_and_unsubscribes(entities):
    async def scenario():
        hass = _Hass(); hass.bus = Bus(); hass.data = {'ha_frigate_privacy':{'storage':Storage()}}
        removers = []; entry = types.SimpleNamespace(async_on_unload=removers.append)
        added = []
        await entities.button.async_setup_entry(hass, entry, lambda items, *args: added.extend(items))
        assert len(added) == 3
        hass.states.values['switch.garden_detect'] = _State('on')
        hass.entity_registry.platforms['switch.garden_detect'] = 'frigate'
        for _ in range(2):
            hass.bus.fire('state_changed', {'entity_id':'switch.garden_detect', 'new_state':object()})
        assert len(added) == 6
        assert len({entity._attr_unique_id for entity in added}) == 6
        assert all(entity._attr_device_info['identifiers'] == {('ha_frigate_privacy', entity._camera_id)} for entity in added)
        for remove in removers: remove()
        assert not hass.bus.listeners
    asyncio.run(scenario())


def test_global_outcome_unknown_until_recorded(entities):
    async def scenario():
        storage = Storage()
        hass = types.SimpleNamespace(data={'ha_frigate_privacy':{'recovery_ready':True}}, bus=Bus())
        sensor = prepare(entities.sensor.FrigatePrivacyOutcome(storage), hass)
        await sensor.async_added_to_hass()
        assert sensor._attr_native_value is None
        for value in ('confirmed','partial','error'):
            storage.outcome = value; await sensor.async_update()
            assert sensor._attr_native_value == value
        storage.outcome = 'invalid'; await sensor.async_update()
        assert sensor._attr_native_value is None
        for remove in sensor.removers: remove()
        assert not hass.bus.listeners
    asyncio.run(scenario())
