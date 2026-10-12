"""Safe bounded privacy-transition projections; no HA I/O or control here."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

SCHEMA = 1
MAX_PERIODS = 200
MAX_DAYS = 30
MAX_BYTES = 1024 * 1024
ID = re.compile(r'^[a-f0-9]{64}$')
CAMERA = re.compile(r'^[a-z0-9_]{1,255}$')
TARGET = re.compile(r'^(switch|camera)\.[a-z0-9_]{1,255}$')
PHASES = {'pausing', 'paused', 'resuming', 'partial', 'error', 'active'}
SOURCES = {'manual', 'schedule', 'unknown'}
REASONS = {'pause_incomplete', 'manual_override', 'admin_request', 'schedule_window_ended',
           'manual_deadline_elapsed', 'restart_recovery', 'restart_during_pause',
           'recovery_targets_missing', 'switch_unavailable', 'resume_failed',
           'resume_cancelled', 'state_persistence_failed', 'invalid_persisted_targets',
           'invalid_persisted_state', 'recovery_pending', 'unknown'}
OUTCOMES = {'pending', 'missing', 'unavailable', 'preexisting_off', 'paused', 'active',
            'service_failed', 'readback_failed', 'failed', 'repaused', 're_pause_readback_failed',
            're_pause_cancelled', 're_pause_service_failed', 'unknown'}
STATES = {'on', 'off', 'idle', 'streaming', 'recording', 'unavailable', 'unknown'}
CHANNELS = {'detection', 'recording', 'snapshots', 'sound_detection', 'motion', 'camera_control'}
SUFFIXES = {'_audio_detection':'sound_detection', '_audio':'sound_detection', '_recordings':'recording',
            '_snapshots':'snapshots', '_detect':'detection', '_motion':'motion',
            '_enabled':'camera_control'}


def utc(value: Any, now: datetime | None = None) -> str | None:
    """Accept only an actual timezone-aware date, never fill missing with now."""
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None or (now is not None and date > now):
            return None
        return date.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, OverflowError):
        return None


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _is(value: Any, choices: set[str]) -> bool:
    return isinstance(value, str) and value in choices


def _reason(value: Any) -> str | None:
    return value if isinstance(value, str) and value in REASONS else ('unknown' if value else None)


def _channel(target: str) -> str:
    if target.startswith('camera.'):
        return 'camera_control'
    return next((name for suffix, name in SUFFIXES.items() if target.endswith(suffix)), 'unknown')


def _outcomes(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {target: outcome if isinstance(outcome, str) and outcome in OUTCOMES else 'unknown'
            for target, outcome in list(value.items())[:256]
            if isinstance(target, str) and TARGET.fullmatch(target)}


def _targets(value: Any) -> list[str]:
    return [item for item in value[:256] if isinstance(item, str) and TARGET.fullmatch(item)] if isinstance(value, list) else []


def _verified_restore(record: dict[str, Any], ended: str | None) -> bool:
    """Terminal proof must cover exact targets and preexisting-off baseline."""
    if not ended or record.get('phase') != 'active' or record.get('active', True) or record.get('overridden'):
        return False
    for field in ('switches', 'preexisting_off'):
        raw = record.get(field, [])
        valid = _targets(raw)
        if not isinstance(raw, list) or len(valid) != len(raw) or len(set(valid)) != len(raw):
            return False
        if any(not target.startswith(f"switch.{record.get('camera_id')}_") for target in valid):
            return False
    if record.get('camera_toggled') and record.get('camera_entity_id') != f"camera.{record.get('camera_id')}":
        return False
    if set(_targets(record.get('switches'))) & set(_targets(record.get('preexisting_off'))):
        return False
    expected = {target:'on' for target in _targets(record.get('switches'))}
    expected.update({target:'off' for target in _targets(record.get('preexisting_off'))})
    camera = record.get('camera_entity_id')
    if record.get('camera_toggled') and isinstance(camera, str) and TARGET.fullmatch(camera):
        if record.get('period_camera_restore_confirmed') is not True:
            return False
        actual_states = record.get('last_verified_actual_state')
        actual_camera = actual_states.get(camera) if isinstance(actual_states, dict) else None
        if not _is(actual_camera, {'on', 'idle', 'streaming', 'recording'}):
            return False
        expected[camera] = actual_camera
    proof = record.get('period_restore_proof')
    actual = record.get('last_verified_actual_state')
    completed = set(_targets(record.get('resume_completed')))
    restore_targets = set(_targets(record.get('switches'))) | ({camera} if record.get('camera_toggled') and isinstance(camera, str) else set())
    return bool(expected) and isinstance(proof, dict) and isinstance(actual, dict) and proof == expected and all(actual.get(target) == state for target,state in expected.items()) and restore_targets <= completed


def project_record(record: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Project existing transition evidence; planned deadline is never an end."""
    camera = record.get('camera_id')
    if not isinstance(camera, str) or not CAMERA.fullmatch(camera):
        raise ValueError('invalid camera identifier')
    started = utc(record.get('period_started_at', record.get('started_at')), now)
    ended = utc(record.get('period_ended_at'), now)
    if record.get('phase') != 'active' or record.get('active', True):
        ended = None
    if started and ended and _date(ended) < _date(started):
        ended = None
    generation = record.get('period_generation')
    generation = generation if type(generation) is int and 0 <= generation <= 2**53-1 else None
    identity = json.dumps([camera, started, generation], separators=(',', ':')).encode()
    pause = _outcomes(record.get('target_outcomes'))
    restore = _outcomes(record.get('resume_target_outcomes'))
    for target in _targets(record.get('failed')):
        pause.setdefault(target, 'failed')
    for target in _targets(record.get('unavailable')):
        pause.setdefault(target, 'unavailable')
    for target in _targets(record.get('resume_failed')):
        restore.setdefault(target, 'failed')
    for target in _targets(record.get('resume_unavailable')):
        restore.setdefault(target, 'unavailable')
    actual = record.get('last_verified_actual_state')
    actual = deepcopy(actual) if isinstance(actual, dict) else {}
    if record.get('period_end_reason') == 'manual_override':
        for target in _targets(record.get('overridden_switches')):
            # Scheduler observed exact switches on. Camera enabled evidence is
            # distinct from a camera's live-video or microphone state.
            actual[target] = 'on' if target.startswith('switch.') else 'unknown'
    verified = _verified_restore(record, ended)
    proof = record.get('period_restore_proof') if verified else {}
    evidence = []
    for target in sorted(pause.keys() | restore.keys() | set(_targets(record.get('overridden_switches'))) | set(proof)):
        pause_outcome = pause.get(target, 'unknown')
        restore_outcome = restore.get(target, 'unknown')
        if verified and target in proof:
            restore_outcome = 'preexisting_off' if proof[target] == 'off' else 'active'
        if target in _targets(record.get('preexisting_off')) and restore_outcome == 'active':
            restore_outcome = 'preexisting_off'
        state = actual.get(target)
        evidence.append({'channel':_channel(target), 'target':target,
            'pause_outcome':pause_outcome, 'restore_outcome':restore_outcome,
            'observed_state':state if isinstance(state, str) and state in STATES else 'unknown',
            'outcomes_seen':sorted(({pause_outcome, restore_outcome}
                | ({'failed'} if target in _targets(record.get('failed')) + _targets(record.get('resume_failed')) else set())
                | ({'unavailable'} if target in _targets(record.get('unavailable')) + _targets(record.get('resume_unavailable')) else set())) - {'unknown'})})
    duration = (datetime.fromisoformat(ended.replace('Z','+00:00')) - datetime.fromisoformat(started.replace('Z','+00:00'))).total_seconds() if started and ended else None
    return {'id':hashlib.sha256(identity).hexdigest(), 'camera_id':camera,
        'generation':generation, 'started_at':started, 'ended_at':ended,
        'planned_ends_at':utc(record.get('ends_at')), 'observed_at':utc(record.get('observed_at'), now),
        'phase':record.get('phase') if _is(record.get('phase'), PHASES) else 'error',
        'source':record.get('source') if _is(record.get('source'), SOURCES) else 'unknown',
        'reason':_reason(record.get('reason')), 'end_reason':_reason(record.get('period_end_reason')) if ended else None,
        'verified_restore':verified, 'duration_seconds':duration,
        'channels':[item for item in evidence if item['channel'] != 'unknown'],
        'unknown_channels':[item for item in evidence if item['channel'] == 'unknown'],
        'evidence_scope':'transition_intent'}



def _restore_channels_consistent(row: dict[str, Any]) -> bool:
    items = row['channels'] + row['unknown_channels']
    if not items or len({item['target'] for item in items}) != len(items):
        return False
    for item in items:
        target = item['target']
        if item['channel'] != _channel(target):
            return False
        if target.startswith('switch.'):
            if not target.startswith(f"switch.{row['camera_id']}_"):
                return False
            expected = 'off' if item['restore_outcome'] == 'preexisting_off' else 'on'
            if item['restore_outcome'] not in {'active','preexisting_off'} or item['observed_state'] != expected:
                return False
        elif target != f"camera.{row['camera_id']}" or item['restore_outcome'] != 'active' or item['observed_state'] not in {'on','idle','streaming','recording'}:
            return False
    return True


def _valid_row(row: Any) -> bool:
    required = {'id','camera_id','generation','started_at','ended_at','planned_ends_at',
                'observed_at','phase','source','reason','end_reason','verified_restore',
                'duration_seconds','channels','unknown_channels','evidence_scope'}
    if not isinstance(row, dict) or not required <= row.keys():
        return False
    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not ID.fullmatch(row['id']) or not isinstance(row.get('camera_id'), str) or not CAMERA.fullmatch(row['camera_id']):
        return False
    if row.get('generation') is not None and (type(row['generation']) is not int or not 0 <= row['generation'] <= 2**53-1):
        return False
    for field in ('started_at','ended_at','planned_ends_at','observed_at'):
        if field not in row or (row[field] is not None and utc(row[field]) != row[field]):
            return False
    if not _is(row.get('phase'), PHASES) or not _is(row.get('source'), SOURCES) or type(row.get('verified_restore')) is not bool or row.get('evidence_scope') != 'transition_intent':
        return False
    if any(row.get(field) is not None and not _is(row[field], REASONS) for field in ('reason','end_reason')):
        return False
    start,end = row['started_at'],row['ended_at']
    duration = row.get('duration_seconds')
    if (end and start and _date(end) < _date(start)) or (row['verified_restore'] and (not end or row.get('phase') != 'active' or row.get('end_reason') == 'manual_override')):
        return False
    expected = (datetime.fromisoformat(end.replace('Z','+00:00'))-datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds() if end and start else None
    if duration != expected or type(duration) is bool:
        return False
    for field in ('channels','unknown_channels'):
        items = row.get(field)
        if not isinstance(items,list) or len(items) > 256:
            return False
        for item in items:
            if not isinstance(item,dict) or not isinstance(item.get('target'),str) or not TARGET.fullmatch(item['target']) or not _is(item.get('channel'), (CHANNELS if field == 'channels' else {'unknown'})):
                return False
            if not _is(item.get('pause_outcome'), OUTCOMES) or not _is(item.get('restore_outcome'), OUTCOMES) or not _is(item.get('observed_state'), STATES):
                return False
            seen = item.get('outcomes_seen', [])
            if not isinstance(seen, list) or len(seen) > len(OUTCOMES) or any(not _is(value, OUTCOMES) for value in seen):
                return False
    if row['verified_restore'] and not _restore_channels_consistent(row):
        return False
    # Unknown row fields are not echoed to clients; only generated schema fields.
    return True


def _decode_unchecked(payload: Any) -> tuple[list[dict[str, Any]], str]:
    if payload is None:
        return [], 'legacy_latest'
    if not isinstance(payload, dict):
        return [], 'corrupt'
    if type(payload.get('schema')) is not int:
        return [], 'corrupt'
    if payload['schema'] != SCHEMA:
        return [], 'unsupported'
    rows = payload.get('periods')
    if not isinstance(rows,list) or len(rows) > MAX_PERIODS or any(not _valid_row(row) for row in rows) or len({row['id'] for row in rows}) != len(rows):
        return [], 'corrupt'
    # Bound payload size even if unknown fields were added to a recognized row.
    if len(json.dumps(payload, ensure_ascii=True).encode()) > MAX_BYTES:
        return [], 'corrupt'
    return deepcopy(rows), 'ready'


def _decode(payload: Any) -> tuple[list[dict[str, Any]], str]:
    try:
        return _decode_unchecked(payload)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return [], 'corrupt'


def retain(rows: list[dict[str, Any]], now: datetime, days: int = MAX_DAYS) -> list[dict[str, Any]]:
    cutoff = now - timedelta(days=days)
    def keep(row: dict[str, Any]) -> bool:
        date = row['ended_at'] or row['started_at']
        return date is None or cutoff <= datetime.fromisoformat(date.replace('Z','+00:00')) <= now
    return sorted((row for row in rows if keep(row)), key=lambda row: _date(row['started_at']) if row['started_at'] else datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:MAX_PERIODS]


def _merge_seen(row: dict[str, Any], prior: dict[str, Any] | None) -> None:
    if not prior:
        return
    previous = {item['target']:item for field in ('channels','unknown_channels') for item in prior[field]}
    for field in ('channels','unknown_channels'):
        for item in row[field]:
            old = previous.get(item['target'], {})
            item['outcomes_seen'] = sorted(set(item['outcomes_seen']) | set(old.get('outcomes_seen', [])))
        # Evidence from removed/failed targets remains available separately.
        present = {item['target'] for item in row[field]}
        row[field].extend(deepcopy(item) for item in prior[field] if item['target'] not in present)
        row[field] = row[field][:256]


def capture(payload: Any, before: dict[str, Any], after: dict[str, Any], now: datetime) -> Any:
    """Return a candidate history payload; caller commits with state atomically."""
    rows,status = _decode(payload)
    if status in {'corrupt','unsupported'}:
        return deepcopy(payload)
    by_id = {row['id']:row for row in rows}
    for camera,record in after.items():
        if record == before.get(camera):
            continue
        for old in ([before[camera]] if camera in before else []):
            try:
                prior = project_record({**old,'camera_id':camera}, now)
            except (ValueError,TypeError):
                continue
            if prior['id'] not in by_id:
                by_id[prior['id']] = prior
        row = project_record({**record,'camera_id':camera}, now)
        prior = by_id.get(row['id'])
        _merge_seen(row, prior)
        by_id[row['id']] = {**deepcopy(prior or {}), **row}
    candidate = deepcopy(payload) if isinstance(payload, dict) else {}
    candidate.update(schema=SCHEMA, periods=retain(list(by_id.values()), now))
    while candidate['periods'] and len(json.dumps(candidate, ensure_ascii=True).encode()) > MAX_BYTES:
        candidate['periods'].pop()
    return candidate


def read_history(payload: Any, current: dict[str, Any], now: datetime, days: int = MAX_DAYS) -> dict[str, Any]:
    """Read-only retention/projection; no physical cleanup or legacy backfill."""
    rows,status = _decode(payload)
    if status == 'legacy_latest':
        for camera,record in list(current.items())[:MAX_PERIODS]:
            try:
                rows.append(project_record({**record,'camera_id':camera}, now))
            except (ValueError,TypeError):
                status = 'corrupt'
                rows = []
                break
    safe_rows=[]
    for row in retain(rows, now, days):
        safe = {key:deepcopy(row[key]) for key in ('id','camera_id','generation','started_at','ended_at','planned_ends_at','observed_at','phase','source','reason','end_reason','verified_restore','duration_seconds','evidence_scope')}
        for field in ('channels','unknown_channels'):
            safe[field] = [{key:deepcopy(item.get(key, [] if key == 'outcomes_seen' else 'unknown')) for key in ('channel','target','pause_outcome','restore_outcome','observed_state','outcomes_seen')} for item in row[field]]
        safe_rows.append(safe)
    return {'schema':SCHEMA, 'status':status, 'periods':safe_rows,
            'retention':{'max_periods':MAX_PERIODS,'max_days':MAX_DAYS,'max_bytes':MAX_BYTES,'read_filtered':True},
            'scope':'latest_records_only' if status == 'legacy_latest' else 'recorded_transitions',
            'days':days}
