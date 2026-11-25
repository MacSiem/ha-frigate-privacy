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
