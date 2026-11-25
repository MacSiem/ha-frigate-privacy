"""Independent feature scopes preserve only their own baseline."""
import asyncio
import pytest
from test_restart_recovery import control, _Hass, _State, _Storage


@pytest.mark.parametrize('scope', ['recordings', 'snapshots', 'detect', 'motion', 'audio_detection', 'review_alerts', 'review_detections', 'camera'])
@pytest.mark.parametrize('initial', ['on', 'off'])
def test_individual_scope_exact_resume(scope, initial):
    async def run():
        hass, storage = _Hass(), _Storage()
        entity = 'camera.front' if scope == 'camera' else 'switch.front_' + scope
        hass.states.values[entity] = _State('streaming' if scope == 'camera' and initial == 'on' else initial)
        hass.entity_registry.platforms[entity] = 'frigate'
        before = {key: value.state for key, value in hass.states.values.items()}
        result = await control.async_pause_camera(hass, storage, 'front', stream_type=scope)
        assert result['phase'] == 'paused'
        assert all(target == entity for _, _, target in hass.services.calls)
        resumed = await control.async_resume_camera(hass, storage, 'front')
        assert resumed['resumed']
        if scope == 'camera' and initial == 'on':
            assert hass.states.get(entity).state in {'idle', 'streaming'}
            before[entity] = hass.states.get(entity).state
        assert {key: value.state for key, value in hass.states.values.items()} == before
    asyncio.run(run())


def test_missing_feature_is_partial_and_discovery_lists_supported():
    async def run():
        hass, storage = _Hass(), _Storage()
        scopes = control.discover_frigate_cameras(hass)[0]['feature_scopes']
        assert 'camera' in scopes and 'detect' in scopes and 'snapshots' not in scopes
        result = await control.async_pause_camera(hass, storage, 'front', stream_type='snapshots')
        assert result['phase'] == 'partial'
        assert storage.paused['front']['target_outcomes']['switch.front_snapshots'] == 'missing'
        assert not hass.services.calls
    asyncio.run(run())


def test_replacement_target_blocks_resume():
    async def run():
        hass, storage = _Hass(), _Storage()
        original = hass.entity_registry.async_get
        identity = {'uid': 'entry:switch:front_detect'}
        # Give every entity coherent upstream metadata.
        def registry_all(entity_id):
            entry = original(entity_id)
            if entry:
                domain, slug = entity_id.split('.', 1)
                entry.config_entry_id = 'entry'
                entry.unique_id = identity['uid'] if entity_id == 'switch.front_detect' else f'entry:{domain}:{slug}'
                entry.device_id = 'device'
            return entry
        hass.entity_registry.async_get = registry_all
        assert (await control.async_pause_camera(hass, storage, 'front', stream_type='detect'))['paused']
        identity['uid'] = 'entry:switch:replacement_detect'
        result = await control.async_resume_camera(hass, storage, 'front')
        assert not result['resumed']
        assert ('switch', 'turn_on', 'switch.front_detect') not in hass.services.calls
    asyncio.run(run())


def test_two_instances_and_renamed_entities_preserve_identity_and_restore():
    async def run():
        hass, storage = _Hass(), _Storage()
        identities = {}
        for entity in list(hass.states.values):
            domain, slug = entity.split('.')
            identities[entity] = ('one', f'one:{domain}:{slug}', 'device-one')
        for entity, uid in [('camera.backyard', 'two:camera:front'), ('switch.backyard_detect', 'two:switch:front_detect'), ('switch.backyard_recordings', 'two:switch:front_recordings')]:
            hass.states.values[entity] = _State('streaming' if entity.startswith('camera.') else 'on')
            hass.entity_registry.platforms[entity] = 'frigate'
            identities[entity] = ('two', uid, 'device-two')
        original = hass.entity_registry.async_get
        def registry(entity):
            entry = original(entity)
            if entry and entity in identities:
                entry.config_entry_id, entry.unique_id, entry.device_id = identities[entity]
            return entry
        hass.entity_registry.async_get = registry
        cameras = control.discover_frigate_cameras(hass)
        assert {item['camera_id'] for item in cameras} == {'one:front', 'two:front'}
        assert not (await control.async_pause_camera(hass, storage, 'front', stream_type='detect'))['paused']
        result = await control.async_pause_camera(hass, storage, 'switch.backyard_detect', stream_type='detect')
        assert result['paused'] and result['camera_id'] == 'two:front'
        assert hass.states.get('switch.front_detect').state == 'on'
        old, new = 'switch.backyard_detect', 'switch.renamed_motion_control'
        hass.states.values[new] = hass.states.values.pop(old)
        hass.entity_registry.platforms[new] = hass.entity_registry.platforms.pop(old)
        identities[new] = identities.pop(old)
        result = await control.async_resume_camera(hass, storage, 'two:front')
        assert result['resumed']
        assert hass.states.get(new).state == 'on'
        assert hass.states.get('switch.front_detect').state == 'on'
    asyncio.run(run())


def test_schedule_expands_feature_pause_to_all_and_restores():
    async def run():
        hass, storage = _Hass(), _Storage()
        assert (await control.async_pause_camera(hass, storage, 'front', stream_type='detect'))['paused']
        result = await control.async_pause_camera(hass, storage, 'front', stream_type='all', source='schedule', schedule_id='schedule')
        assert result['paused']
        assert hass.states.get('switch.front_recordings').state == 'off'
        assert hass.states.get('camera.front').state == 'off'
        result = await control.async_resume_camera(hass, storage, 'front', authority=control.ResumeAuthority.SCHEDULE)
        assert result['resumed']
        assert hass.states.get('switch.front_detect').state == 'on'
        assert hass.states.get('switch.front_recordings').state == 'on'
    asyncio.run(run())
