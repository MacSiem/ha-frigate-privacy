"""Coverage is metadata only and never exposes stream configuration."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('coverage', Path('custom_components/ha_frigate_privacy/stream_coverage.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_topology_and_prefix_collision():
    config = {'cameras': {'front': {'live': {'streams': {'Main': 'shared'}}, 'ffmpeg': {'inputs': [{'path': 'rtsp://127.0.0.1:8554/front_sub?secret=1'}]}}, 'front_door': {}}, 'go2rtc': {'streams': {'front': 'secret', 'front_sub': 'secret', 'front_door': 'secret', 'front_door_low': 'secret', 'shared': 'secret'}}}
    assert m.stream_coverage(config, 'front') == {'status': 'best_effort', 'count': 3}
    assert m.stream_coverage(config, 'front_door') == {'status': 'best_effort', 'count': 2}
    assert 'secret' not in str(m.stream_coverage(config, 'front'))


def test_unknown_and_ambiguous_foreign_ownership():
    assert m.stream_coverage(None, 'front') == {'status': 'unknown'}
    assert m.stream_coverage({'cameras': {'front': {}}, 'go2rtc': {'streams': []}}, 'front') == {'status': 'unknown'}
    config = {'cameras': {'front': {'live': {'streams': {'A': 'shared'}}}, 'back': {'live': {'streams': {'B': 'shared', 'C': 'front_foreign'}}}}, 'go2rtc': {'streams': {'shared': 'secret', 'front_foreign': 'secret'}}}
    assert m.stream_coverage(config, 'front') == {'status': 'best_effort', 'count': 0}
    assert m.stream_coverage(config, 'back') == {'status': 'best_effort', 'count': 1}


def test_discovery_uses_only_owned_entry_and_refreshes():
    import json
    import types
    fixture_spec = importlib.util.spec_from_file_location('recovery_fixture', Path('tests/test_restart_recovery.py'))
    fixture = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture)
    hass = fixture._Hass()
    hass.states.values['camera.front'].attributes['camera_name'] = 'front'
    original = hass.entity_registry.async_get
    def registry(entity_id):
        entry = original(entity_id)
        if entry:
            entry.config_entry_id = 'own'
            entry.device_id = 'device-own'
            domain, slug = entity_id.split('.', 1)
            entry.unique_id = f'own:{domain}:{slug}'
        return entry
    hass.entity_registry.async_get = registry
    hass.data = {'frigate': {'own': {'config': {'cameras': {'front': {}}, 'go2rtc': {'streams': {'front': 'secret'}}}}, 'other': {'config': {'cameras': {'front': {}}, 'go2rtc': {'streams': {'front': 'secret', 'front_sub': 'secret'}}}}}}
    result = fixture.control.discover_frigate_cameras(hass)[0]
    assert result['stream_coverage'] == {'status': 'best_effort', 'count': 1}
    assert 'secret' not in json.dumps(result)
    hass.data['frigate']['own']['config']['go2rtc']['streams']['front_sub'] = 'secret'
    assert fixture.control.discover_frigate_cameras(hass)[0]['stream_coverage']['count'] == 2
    hass.entity_registry.platforms['camera.front'] = 'foreign'
    assert fixture.control.discover_frigate_cameras(hass)[0]['stream_coverage'] == {'status': 'unknown'}


def test_conflicting_instances_and_suffixed_entities_fail_closed():
    import importlib.util
    import asyncio
    spec = importlib.util.spec_from_file_location('recovery_fixture', Path('tests/test_restart_recovery.py'))
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    hass = fixture._Hass()
    hass.states.values['camera.front'].attributes['camera_name'] = 'front'
    original = hass.entity_registry.async_get
    identities = {
        'camera.front': ('one', 'device-one', 'one:camera:front'),
        'switch.front_detect': ('two', 'device-two', 'two:switch:front_detect'),
        'switch.front_recordings': ('one', 'device-one', 'one:switch:front_recordings'),
    }
    def registry(entity_id):
        entry = original(entity_id)
        if entry and entity_id in identities:
            entry.config_entry_id, entry.device_id, entry.unique_id = identities[entity_id]
        return entry
    hass.entity_registry.async_get = registry
    hass.data = {'frigate': {'one': {'config': {'cameras': {'front': {}}, 'go2rtc': {'streams': {'front': 'private'}}}}, 'two': {'config': {'cameras': {'front': {}}, 'go2rtc': {'streams': {'front': 'private', 'front_sub': 'private'}}}}}}
    assert fixture.control.discover_frigate_cameras(hass) == []
    assert not asyncio.run(fixture.control.async_pause_camera(hass, fixture._Storage(), 'front'))['paused']
    assert hass.services.calls == []
    assert not fixture.control._persisted_targets_are_valid(hass, 'front', ['switch.front_recordings', 'switch.front_detect'], 'camera.front', True)
    identities['switch.front_detect'] = ('one', 'device-one', 'one:switch:front_detect')
    assert fixture.control.discover_frigate_cameras(hass)[0]['stream_coverage']['count'] == 1
    identities['switch.front_detect'] = ('one', 'device-one', 'one:switch:front_2_detect')
    assert fixture.control.discover_frigate_cameras(hass) == []


def test_audio_detection_registry_identity_matches_upstream_audio():
    spec = importlib.util.spec_from_file_location('recovery_fixture', Path('tests/test_restart_recovery.py'))
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    hass = fixture._Hass()
    hass.states.values['camera.front'].attributes['camera_name'] = 'front'
    hass.states.values['switch.front_audio_detection'] = fixture._State('on')
    hass.entity_registry.platforms['switch.front_audio_detection'] = 'frigate'
    original = hass.entity_registry.async_get
    identity = {'suffix': 'audio'}
    def registry(entity_id):
        entry = original(entity_id)
        if entry:
            domain, slug = entity_id.split('.', 1)
            if entity_id == 'switch.front_audio_detection':
                slug = 'front_' + identity['suffix']
            entry.config_entry_id = 'own'
            entry.device_id = 'device-own'
            entry.unique_id = f'own:{domain}:{slug}'
        return entry
    hass.entity_registry.async_get = registry
    for suffix in ('audio', 'audio_detection'):
        identity['suffix'] = suffix
        cameras = fixture.control.discover_frigate_cameras(hass)
        assert len(cameras) == 1
        assert 'switch.front_audio_detection' in cameras[0]['available_switches']
        assert fixture.control._persisted_targets_are_valid(hass, 'front', ['switch.front_audio_detection'], 'camera.front', True)
    identity['suffix'] = 'other_audio'
    assert fixture.control.discover_frigate_cameras(hass) == []
