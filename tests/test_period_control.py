"""Actual control path + actual storage producer, using existing HA fixtures."""
import asyncio
from copy import deepcopy
import pytest
from test_period_storage import storage_module
from test_restart_recovery import control, _Hass, _State


def test_pause_resume_next_pause_keeps_terminal_period_and_exact_proof(storage_module):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        paused = await control.async_pause_camera(hass,storage,'front',duration_minutes=30,operation_id='period-pause-1')
        assert paused['phase'] == 'paused'
        first = (await storage.async_get_periods())['periods'][0]
        assert first['ended_at'] is None
        resumed = await control.async_resume_camera(hass,storage,'front',operation_id='period-resume-1')
        assert resumed['resumed'] is True
        rows = (await storage.async_get_periods())['periods']
        assert len(rows) == 1 and rows[0]['id'] == first['id']
        assert rows[0]['verified_restore'] is True and rows[0]['ended_at'] is not None
        completed = rows[0]
        await control.async_resume_camera(hass,storage,'front',operation_id='period-resume-1')
        assert (await storage.async_get_periods())['periods'] == rows
        await control.async_pause_camera(hass,storage,'front',duration_minutes=30,operation_id='period-pause-2')
        rows = (await storage.async_get_periods())['periods']
        assert len(rows) == 2 and completed in rows
    asyncio.run(scenario())


def test_terminal_history_save_failure_reuses_existing_physical_fail_safe(storage_module):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        await control.async_pause_camera(hass,storage,'front',duration_minutes=30)
        original = storage._store.async_save
        async def fail_terminal(data):
            if data['paused']['front']['phase'] == 'active':
                raise storage_module.StorageWriteError('synthetic terminal save failure')
            await original(data)
        storage._store.async_save = fail_terminal
        result = await control.async_resume_camera(hass,storage,'front')
        assert result['resumed'] is False
        assert hass.states.get('switch.front_detect').state == 'off'
        assert hass.states.get('switch.front_recordings').state == 'off'
        rows = (await storage.async_get_periods())['periods']
        assert len(rows) == 1 and rows[0]['ended_at'] is None
        assert rows[0]['verified_restore'] is False
    asyncio.run(scenario())


@pytest.mark.parametrize("recordings,snapshots", [("on", "on"), ("on", "off"), ("off", "on"), ("off", "off")])
@pytest.mark.parametrize("restart", [False, True])
def test_recordings_and_snapshots_restore_exact_baseline(storage_module, recordings, snapshots, restart):
    """Reload serialized real storage; no real HA restart or camera is involved."""
    async def scenario():
        hass = _Hass()
        hass.states.values["switch.front_recordings"].state = recordings
        hass.states.values["switch.front_snapshots"] = _State(snapshots)
        hass.entity_registry.platforms["switch.front_snapshots"] = "frigate"
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        paused = await control.async_pause_camera(hass, storage, "front", duration_minutes=30)
        assert paused["phase"] == "paused"
        for suffix in ("recordings", "snapshots"):
            assert hass.states.get("switch.front_" + suffix).state == "off"
        if restart:
            # Persist the actual producer's pause record at the interrupted resume boundary.
            await storage.async_transition_paused("front", "resuming")
            reloaded = storage_module.FrigatePrivacyStorage(hass)
            reloaded._store.saved = deepcopy(storage._store.saved)
            await reloaded.async_load()
            storage = reloaded
            assert (await control.async_recover_transitions(hass, storage))["recovered"] == ["front"]
        else:
            assert (await control.async_resume_camera(hass, storage, "front"))["resumed"] is True
        for suffix, baseline in (("recordings", recordings), ("snapshots", snapshots)):
            entity = "switch.front_" + suffix
            assert hass.states.get(entity).state == baseline
            assert hass.services.calls.count(("switch", "turn_on", entity)) == (1 if baseline == "on" else 0)
        periods = (await storage.async_get_periods())["periods"]
        assert len(periods) == 1 and periods[0]["verified_restore"] is True
        assert periods[0]["ended_at"] is not None
        calls = list(hass.services.calls)
        assert (await control.async_recover_transitions(hass, storage))["recovered"] == []
        assert hass.services.calls == calls
    asyncio.run(scenario())


@pytest.mark.parametrize("source", ["manual", "schedule"])
@pytest.mark.parametrize("entry_ids", [("one", "two"), ("01HFIRSTENTRY", "01HSECONDENTRY")])
def test_two_entries_round_trip_period_history_and_export(storage_module, source, entry_ids):
    """Both qualified identities survive every durable history transition."""
    import json
    async def scenario():
        hass = _Hass()
        identities = {}
        first, second = entry_ids
        qualified = {control._identity_qualifier(first) + ':front', control._identity_qualifier(second) + ':front'}
        for entity in list(hass.states.values):
            domain, slug = entity.split('.')
            identities[entity] = (first, f'{first}:{domain}:{slug}', 'device-one')
        for entity, uid in [('camera.other', f'{second}:camera:front'), ('switch.other_detect', f'{second}:switch:front_detect')]:
            hass.states.values[entity] = _State('streaming' if entity.startswith('camera.') else 'on')
            hass.entity_registry.platforms[entity] = 'frigate'
            identities[entity] = (second, uid, 'device-two')
        original = hass.entity_registry.async_get
        def registry(entity):
            entry = original(entity)
            if entry and entity in identities:
                entry.config_entry_id, entry.unique_id, entry.device_id = identities[entity]
            return entry
        hass.entity_registry.async_get = registry
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        for camera in qualified:
            result = await control.async_pause_cameras(hass, storage, [camera], stream_type='detect', source=source, schedule_id='schedule' if source == 'schedule' else None)
            assert result['ok']
            assert (await control.async_resume_camera(hass, storage, camera, authority=control.ResumeAuthority.SCHEDULE if source == 'schedule' else control.ResumeAuthority.ADMIN))['resumed']
        history = await storage.async_get_periods()
        assert history['status'] == 'ready'
        assert {row['camera_id'] for row in history['periods']} == qualified
        assert all(row['ended_at'] and not row['verified_restore'] for row in history['periods'])
        exported = json.loads(json.dumps(history))
        assert {row['camera_id'] for row in exported['periods']} == qualified
        reloaded = storage_module.FrigatePrivacyStorage(hass)
        reloaded._store.saved = deepcopy(storage._store.saved)
        await reloaded.async_load()
        assert (await reloaded.async_get_periods())['status'] == 'ready'
    asyncio.run(scenario())


def test_upstream_names_aliases_collision_rename_and_real_history(storage_module):
    """Uppercase and hyphen names must not collapse onto HA slug aliases."""
    async def scenario():
        hass = _Hass()
        hass.states.values.clear()
        hass.entity_registry.platforms.clear()
        identities = {}
        for slug, logical in [('front_yard', 'Front-Yard'), ('front_yard_2', 'front-yard'), ('front_yard_3', 'front_yard')]:
            for domain, suffix in [('camera', ''), ('switch', '_detect'), ('switch', '_snapshots')]:
                entity = f'{domain}.{slug}{suffix}'
                hass.states.values[entity] = _State('streaming' if domain == 'camera' else 'on')
                if domain == 'camera':
                    hass.states.values[entity].attributes['camera_name'] = logical
                hass.entity_registry.platforms[entity] = 'frigate'
                identities[entity] = ('one', f'one:{domain}:{logical}{suffix}', 'device-' + logical)
        original = hass.entity_registry.async_get
        def registry(entity):
            entry = original(entity)
            if entry and entity in identities:
                entry.config_entry_id, entry.unique_id, entry.device_id = identities[entity]
            return entry
        hass.entity_registry.async_get = registry
        hass.data = {'frigate': {'one': {'config': {'cameras': {'Front-Yard': {'live': {'streams': {'Main':'yard_stream'}}}}, 'go2rtc': {'streams': {'yard_stream':'private'}}}}}}
        cameras = control.discover_frigate_cameras(hass)
        ids = {c['camera_id'] for c in cameras}
        upper = control._logical_camera_token('Front-Yard')
        hyphen = control._logical_camera_token('front-yard')
        assert ids == {upper, hyphen, 'front_yard'}
        assert next(c for c in cameras if c['camera_id'] == upper)['stream_coverage']['count'] == 1
        assert control._resolve_camera_ref(hass, 'Front-Yard') == upper
        assert control._resolve_camera_ref(hass, 'front-yard') == hyphen
        assert control._resolve_camera_ref(hass, 'camera.front_yard') == upper
        assert control._resolve_camera_ref(hass, 'front_yard') == 'front_yard'
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        assert (await control.async_pause_camera(hass, storage, 'Front-Yard', stream_type='snapshots'))['paused']
        assert hass.states.get('switch.front_yard_snapshots').state == 'off'
        assert hass.states.get('switch.front_yard_2_snapshots').state == 'on'
        old, new = 'switch.front_yard_snapshots', 'switch.changed_snapshot_entity'
        hass.states.values[new] = hass.states.values.pop(old)
        hass.entity_registry.platforms[new] = hass.entity_registry.platforms.pop(old)
        identities[new] = identities.pop(old)
        assert (await control.async_resume_camera(hass, storage, 'camera.front_yard'))['resumed']
        assert hass.states.get(new).state == 'on'
        history = await storage.async_get_periods()
        assert history['status'] == 'ready' and history['periods'][0]['camera_id'] == upper
        # A pre-identity snapshot under the old slug must never attach to the
        # separate camera whose logical name happens to equal that slug.
        legacy = storage_module.FrigatePrivacyStorage(hass)
        await legacy.async_load()
        hass.states.values[new].state = 'off'
        await legacy.async_set_paused('front_yard', {'phase':'paused', 'active':True,
            'camera_entity_id':'camera.front_yard', 'switches':[new], 'camera_toggled':False})
        view = control.project_camera_records(hass, await legacy.async_get_state())
        assert set(view['paused']) == {upper}
        conflict = await control.async_resume_camera(hass, legacy, 'front_yard')
        assert not conflict['resumed'] and conflict['decision']['reason'] == 'identity_conflict'
        assert hass.states.get(new).state == 'off'
        assert (await control.async_resume_camera(hass, legacy, 'Front-Yard'))['resumed']
        assert hass.states.get(new).state == 'on'
    asyncio.run(scenario())


def test_qualified_raw_name_stays_valid_after_second_instance_disappears(storage_module):
    async def scenario():
        hass = _Hass()
        hass.states.values.clear()
        hass.entity_registry.platforms.clear()
        identities = {}
        for entry, slug in [('one', 'yard_a'), ('two', 'yard_b')]:
            for domain, suffix in [('camera', ''), ('switch', '_detect')]:
                entity = f'{domain}.{slug}{suffix}'
                hass.states.values[entity] = _State('streaming' if domain == 'camera' else 'on')
                if domain == 'camera': hass.states.values[entity].attributes['camera_name'] = 'Front-Yard'
                hass.entity_registry.platforms[entity] = 'frigate'
                identities[entity] = (entry, f'{entry}:{domain}:Front-Yard{suffix}', 'device-' + entry)
        original = hass.entity_registry.async_get
        def registry(entity):
            result = original(entity)
            if result and entity in identities:
                result.config_entry_id, result.unique_id, result.device_id = identities[entity]
            return result
        hass.entity_registry.async_get = registry
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        token = control._logical_camera_token('Front-Yard')
        assert set(control._identity_groups(hass)) == {'one:' + token, 'two:' + token}
        assert not (await control.async_pause_camera(hass, storage, 'Front-Yard', stream_type='detect'))['paused']
        assert (await control.async_pause_camera(hass, storage, 'one:' + token, stream_type='detect'))['paused']
        for entity in ('camera.yard_b', 'switch.yard_b_detect'):
            del hass.states.values[entity]
            del hass.entity_registry.platforms[entity]
            del identities[entity]
        assert (await control.async_resume_camera(hass, storage, 'Front-Yard'))['resumed']
        assert hass.states.get('switch.yard_a_detect').state == 'on'
        assert (await storage.async_get_periods())['status'] == 'ready'
    asyncio.run(scenario())
