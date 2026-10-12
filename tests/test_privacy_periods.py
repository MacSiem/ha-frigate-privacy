"""Synthetic behavior tests for the actual bounded period projection."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'custom_components/ha_frigate_privacy/periods.py'
spec = importlib.util.spec_from_file_location('frigate_period_projection_test', SOURCE)
periods = importlib.util.module_from_spec(spec)
spec.loader.exec_module(periods)
NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def record(**updates):
    value = {'camera_id':'front', 'started_at':'2026-10-12T18:00:00+00:00',
             'period_generation':1, 'generation':1, 'phase':'paused', 'active':True,
             'source':'manual', 'ends_at':'2026-10-12T18:30:00+00:00',
             'switches':['switch.front_detect'], 'target_outcomes':{'switch.front_detect':'paused'}}
    value.update(updates)
    return value


def test_intent_not_deadline_and_no_open_duration():
    row = periods.project_record(record(), NOW)
    assert row['started_at'] == '2026-10-12T18:00:00Z'
    assert row['planned_ends_at'] == '2026-10-12T18:30:00Z'
    assert row['ended_at'] is None
    assert row['duration_seconds'] is None
    assert row['verified_restore'] is False


def test_generations_retry_upsert_and_next_pause_retains_previous():
    first = record()
    payload = periods.capture(None, {}, {'front':first}, NOW)
    retry = record(generation=2, phase='resuming')
    payload = periods.capture(payload, {'front':first}, {'front':retry}, NOW)
    assert len(payload['periods']) == 1
    second = record(started_at='2026-10-12T19:00:00Z', period_generation=3, generation=3)
    payload = periods.capture(payload, {'front':retry}, {'front':second}, NOW)
    assert len(payload['periods']) == 2
    assert len({row['id'] for row in payload['periods']}) == 2


def test_manual_intervention_and_legacy_dates_are_truthful():
    row = periods.project_record(record(phase='active', active=False, overridden=True,
        period_ended_at='2026-10-12T18:20:00Z', period_end_reason='manual_override'), NOW)
    assert row['ended_at'] == '2026-10-12T18:20:00Z'
    assert row['end_reason'] == 'manual_override'
    assert row['verified_restore'] is False
    assert row['duration_seconds'] == 1200
    legacy = periods.project_record({'camera_id':'front','phase':'active','ends_at':NOW.isoformat()}, NOW)
    assert legacy['started_at'] is None and legacy['ended_at'] is None
    assert legacy['duration_seconds'] is None


def test_restore_requires_all_exact_readbacks_and_completed_targets():
    state = record(phase='active', active=False, period_ended_at='2026-10-12T18:20:00Z',
        period_end_reason='admin_request', period_restore_proof={'switch.front_detect':'on'},
        resume_completed=['switch.front_detect'], last_verified_actual_state={'switch.front_detect':'on'})
    assert periods.project_record(state, NOW)['verified_restore'] is True
    state['last_verified_actual_state']['switch.front_detect'] = 'unavailable'
    assert periods.project_record(state, NOW)['verified_restore'] is False
    state['last_verified_actual_state']['switch.front_detect'] = 'on'
    state['preexisting_off'] = ['switch.front_recordings']
    assert periods.project_record(state, NOW)['verified_restore'] is False


def test_channels_do_not_infer_microphone_video_or_drop_unknown_failure():
    row = periods.project_record(record(target_outcomes={
        'switch.front_detect':'paused', 'switch.front_custom':'service_failed',
        'camera.front':'paused', 'https://private.invalid/image':'secret exception'}), NOW)
    assert {item['channel'] for item in row['channels']} == {'detection','camera_control'}
    assert row['unknown_channels'][0]['pause_outcome'] == 'service_failed'
    assert 'https' not in str(row) and 'secret exception' not in str(row)
    assert 'microphone' not in {item['channel'] for item in row['channels']}


def test_strict_schema_and_corruption_not_silent_empty():
    for payload, status in (({'schema':2,'periods':[]},'unsupported'),
                            ({'schema':1,'periods':'broken'},'corrupt'),
                            ({'schema':1,'periods':[{'id':'broken'}]},'corrupt')):
        assert periods.read_history(payload, {}, NOW)['status'] == status
        assert periods.capture(payload, {}, {'front':record()}, NOW) == payload
    result = periods.read_history(None, {'front':record(started_at=None)}, NOW)
    assert result['status'] == 'legacy_latest'
    assert result['periods'][0]['started_at'] is None


def test_bound_count_expiry_utc_and_future_dates():
    payload = None
    before = {}
    for index in range(220):
        state = record(period_generation=index, started_at=(NOW-timedelta(minutes=index)).isoformat())
        payload = periods.capture(payload, before, {'front':state}, NOW)
        before = {'front':state}
    assert len(payload['periods']) == 200
    copy = repr(payload)
    assert periods.read_history(payload, {}, NOW+timedelta(days=31))['periods'] == []
    assert repr(payload) == copy
    row = periods.project_record(record(started_at='2099-01-01T00:00:00Z'), NOW)
    assert row['started_at'] is None
    row = periods.project_record(record(started_at='2026-10-12T20:00:00+02:00'), NOW)
    assert row['started_at'] == '2026-10-12T18:00:00Z'


def test_fractional_utc_order_and_failed_attempt_evidence_survives_retry():
    state = record(started_at='2026-10-12T18:00:00Z', phase='active', active=False,
        period_ended_at='2026-10-12T18:00:00.500000Z')
    row = periods.project_record(state,NOW)
    assert row['duration_seconds'] == .5
    first = record(resume_target_outcomes={'switch.front_detect':'re_pause_service_failed'})
    payload = periods.capture(None,{}, {'front':first},NOW)
    second = record(resume_target_outcomes={'switch.front_detect':'active'})
    payload = periods.capture(payload,{'front':first},{'front':second},NOW)
    assert 're_pause_service_failed' in payload['periods'][0]['channels'][0]['outcomes_seen']


def test_malformed_nested_values_are_corrupt_not_exception_or_success():
    row = periods.project_record(record(),NOW)
    for key in ('phase','reason','channels'):
        broken = {**row,key:{'unsafe':'opaque'}}
        result = periods.read_history({'schema':1,'periods':[broken]}, {}, NOW)
        assert result['status'] == 'corrupt' and result['periods'] == []


def test_unknown_persisted_fields_preserved_but_not_exposed():
    initial = record()
    payload = periods.capture(None, {}, {'front':initial}, NOW)
    payload['future_config'] = {'keep':True}
    payload['periods'][0]['future_row'] = {'keep':True}
    updated = record(phase='partial')
    result = periods.capture(payload, {'front':initial}, {'front':updated}, NOW)
    assert result['future_config'] == {'keep':True}
    assert result['periods'][0]['future_row'] == {'keep':True}
    assert 'future_row' not in periods.read_history(result,{},NOW)['periods'][0]


def test_resume_blocked_channel_is_not_dropped_and_override_does_not_reuse_old_off_readback():
    row = periods.project_record(record(phase='error',resume_unavailable=['switch.front_detect']),NOW)
    assert row['channels'][0]['restore_outcome'] == 'unavailable'
    row = periods.project_record(record(phase='active',active=False,overridden=True,
        overridden_switches=['switch.front_detect'],last_verified_actual_state={'switch.front_detect':'off'},
        period_ended_at='2026-10-12T19:00:00Z',period_end_reason='manual_override'),NOW)
    assert row['channels'][0]['observed_state'] == 'on'
    assert row['verified_restore'] is False


def test_required_fields_missing_or_active_restore_proof_in_error_is_corrupt():
    valid = periods.project_record(record(),NOW)
    for key in ('generation','reason','end_reason','duration_seconds'):
        broken = dict(valid)
        broken.pop(key)
        assert periods.read_history({'schema':1,'periods':[broken]}, {}, NOW)['status'] == 'corrupt'
    broken = {**valid,'phase':'error','verified_restore':True,'ended_at':'2026-10-12T19:00:00Z','duration_seconds':3600}
    assert periods.read_history({'schema':1,'periods':[broken]}, {}, NOW)['status'] == 'corrupt'


def test_camera_restore_requires_existing_confirmation_not_camera_ack():
    state = record(camera_entity_id='camera.front',camera_toggled=True,phase='active',active=False,
        period_ended_at='2026-10-12T19:00:00Z',period_end_reason='admin_request',
        period_restore_proof={'switch.front_detect':'on','camera.front':'idle'},
        resume_completed=['switch.front_detect','camera.front'],
        last_verified_actual_state={'switch.front_detect':'on','camera.front':'idle'})
    assert periods.project_record(state,NOW)['verified_restore'] is False
    state['period_camera_restore_confirmed'] = True
    assert periods.project_record(state,NOW)['verified_restore'] is True


def test_legacy_control_generation_is_not_invented_pause_generation():
    state = record()
    state.pop('period_generation')
    state['generation'] = 7
    assert periods.project_record(state,NOW)['generation'] is None


def test_invalid_or_duplicate_exact_targets_cannot_prove_restore():
    state = record(phase='active',active=False,period_ended_at='2026-10-12T19:00:00Z',
        period_restore_proof={'switch.front_detect':'on'},resume_completed=['switch.front_detect'],
        last_verified_actual_state={'switch.front_detect':'on'})
    for targets in (['switch.front_detect','https://private.invalid'], ['switch.front_detect','switch.front_detect']):
        state['switches'] = targets
        assert periods.project_record(state,NOW)['verified_restore'] is False


def test_fail_safe_repause_keeps_original_failure_evidence():
    state = record(phase='error',resume_failed=['switch.front_detect'],
        resume_target_outcomes={'switch.front_detect':'repaused'})
    row = periods.project_record(state,NOW)
    assert row['channels'][0]['restore_outcome'] == 'repaused'
    assert 'failed' in row['channels'][0]['outcomes_seen']
