"""Real storage methods with isolated, synthetic HA persistence fixtures."""
import asyncio
import importlib.util
import json
import sys
import types
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import pytest

PKG = Path(__file__).resolve().parents[1] / 'custom_components/ha_frigate_privacy'


@pytest.fixture
def storage_module(monkeypatch):
    class CoreState:
        stopping = 'stopping'
    core = types.ModuleType('homeassistant.core')
    core.HomeAssistant = object
    core.CoreState = CoreState
    helper = types.ModuleType('homeassistant.helpers.storage')
    class Store:
        def __init__(self, hass, *args, **kwargs):
            self.hass = hass
            self.saved = None
            self.failure = None
            self.skipped = False
            self.old_hook = False
        async def async_load(self):
            return deepcopy(self.saved)
        async def async_save(self, data):
            if self.skipped:
                return
            try:
                await self._async_write_data(*(['synthetic-path',data] if self.old_hook else [data]))
            except OSError:
                pass
        async def _async_write_data(self, *args, **kwargs):
            if self.failure:
                raise OSError('synthetic IO failure')
            self.saved = deepcopy(args[-1])
    helper.Store = Store
    monkeypatch.setitem(sys.modules,'homeassistant.core',core)
    monkeypatch.setitem(sys.modules,'homeassistant.helpers.storage',helper)
    package = types.ModuleType('period_storage_test')
    package.__path__ = [str(PKG)]
    monkeypatch.setitem(sys.modules,'period_storage_test',package)
    for name in ('const','replay','periods','storage'):
        spec = importlib.util.spec_from_file_location('period_storage_test.'+name,PKG/(name+'.py'))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,spec.name,module)
        spec.loader.exec_module(module)
    return module


def start(generation=1):
    return {'started_at':datetime.now(timezone.utc).isoformat(), 'generation':generation,
            'period_generation':generation, 'phase':'pausing','target_outcomes':{'switch.front_detect':'pending'}}


def test_actual_write_confirmation_stop_skip_swallowed_and_both_hook_shapes(storage_module):
    async def scenario():
        hass = types.SimpleNamespace(state='running')
        store = storage_module._ConfirmedStore(hass,1,'synthetic',private=True,atomic_writes=True)
        for old in (False,True):
            store.old_hook = old
            await store.async_save({'value':old})
            assert store.saved == {'value':old}
        for option in ('failure','skipped'):
            setattr(store,option,True)
            with pytest.raises(storage_module.StorageWriteError):
                await store.async_save({'unexpected':True})
            setattr(store,option,False)
        hass.state = 'stopping'
        with pytest.raises(storage_module.StorageWriteError):
            await store.async_save({'unexpected':True})
    asyncio.run(scenario())


def test_atomic_rollback_restart_and_reads_never_save(storage_module):
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace(state='running'))
        await storage.async_load()
        await storage.async_set_paused('front',start())
        durable = deepcopy(storage._store.saved)
        storage._store.failure = True
        with pytest.raises(storage_module.StorageWriteError):
            await storage.async_transition_paused('front','partial',failed=['switch.front_detect'])
        assert await storage.async_load() == durable
        assert (await storage.async_get_periods())['durability'] == 'save_failed'
        storage._store.failure = False
        await storage.async_set_paused('front',start(3))
        serialized = json.loads(json.dumps(storage._store.saved))
        restarted = storage_module.FrigatePrivacyStorage(types.SimpleNamespace(state='running'))
        restarted._store.saved = serialized
        await restarted.async_load()
        before = deepcopy(restarted._store.saved)
        rows = await restarted.async_get_periods()
        assert len(rows['periods']) == 2
        assert await restarted.async_get_periods() == rows
        assert restarted._store.saved == before
        assert 'schedule_operation_filter' in before
    asyncio.run(scenario())


def test_corrupt_future_payload_preserved_while_control_saves(storage_module):
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace(state='running'))
        storage._store.saved = {'privacy_periods':{'schema':99,'opaque':'keep'}, 'unknown':{'keep':True}}
        await storage.async_load()
        await storage.async_set_paused('front',start())
        assert storage._store.saved['privacy_periods'] == {'schema':99,'opaque':'keep'}
        assert storage._store.saved['unknown'] == {'keep':True}
        assert (await storage.async_get_periods())['status'] == 'unsupported'
    asyncio.run(scenario())


def test_legacy_unknown_start_and_generation_remain_unknown_after_terminal_transition(storage_module):
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace(state='running'))
        storage._store.saved = {'paused':{'front':{'phase':'paused','generation':7}}}
        await storage.async_load()
        await storage.async_mark_overridden('front',on_switches=['switch.front_detect'])
        row = (await storage.async_get_periods())['periods'][0]
        assert row['started_at'] is None and row['generation'] is None
        assert row['duration_seconds'] is None and row['verified_restore'] is False
        assert row['end_reason'] == 'manual_override'
    asyncio.run(scenario())
