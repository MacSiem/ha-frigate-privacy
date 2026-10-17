"""Behavioral extension regressions with real control/storage and synthetic HA."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from test_period_storage import storage_module
from test_restart_recovery import control, _Hass


def test_extension_preserves_snapshot_scope_and_original_period(storage_module):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        await control.async_pause_camera(hass, storage, 'front', duration_minutes=30, stream_type='main')
        before = await storage.async_get_record('front')
        calls = list(hass.services.calls)
        result = await control.async_extend_privacy(hass, storage, ['front', 'camera.front'], duration_minutes=15, operation_id='add-time')
        after = await storage.async_get_record('front')
        assert result['ok']
        assert datetime.fromisoformat(after['ends_at']) - datetime.fromisoformat(before['ends_at']) == timedelta(minutes=15)
        for key in before.keys() - {'ends_at', 'generation', 'operation_history', 'updated_at'}:
            assert after[key] == before[key], key
        assert calls == hass.services.calls
        assert len((await storage.async_get_periods())['periods']) == 1
        assert (await storage.async_get_state())['last_outcome'] == 'confirmed'
        again = await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=15, operation_id='add-time')
        assert again['results'][0]['replayed']
        assert (await storage.async_get_record('front'))['ends_at'] == after['ends_at']
        mismatch = await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=30, operation_id='add-time')
        assert mismatch['results'][0]['reason'] == 'operation_payload_mismatch'
        assert (await storage.async_get_record('front'))['ends_at'] == after['ends_at']
        assert hass.services.calls == calls
    asyncio.run(scenario())


@pytest.mark.parametrize('change,reason', [
    ({'ends_at':None}, 'finite_deadline_required'),
    ({'ends_at':'broken'}, 'finite_deadline_required'),
    ({'ends_at':'2030-01-01T00:00:00'}, 'finite_deadline_required'),
    ({'ends_at':'2000-01-01T00:00:00+00:00'}, 'deadline_elapsed'),
    ({'phase':'error'}, 'privacy_not_extendable'),
    ({'resume_blocked':True}, 'privacy_not_extendable'),
    ({'source':'schedule'}, 'schedule_owned'),
])
def test_rejected_extension_never_changes_targets_or_deadline(storage_module, change, reason):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        await control.async_pause_camera(hass, storage, 'front', duration_minutes=30)
        record = await storage.async_get_record('front')
        record.update(change)
        await storage.async_set_paused('front', record)
        before = await storage.async_get_record('front')
        calls = list(hass.services.calls)
        result = await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=15)
        assert result['results'][0]['reason'] == reason
        assert await storage.async_get_record('front') == before
        assert hass.services.calls == calls
        assert (await storage.async_get_state())['last_outcome'] == 'error'
    asyncio.run(scenario())


@pytest.mark.parametrize('minutes', [0, -1, 1441, True, 1.5, '15', None])
def test_invalid_extension_duration(storage_module, minutes):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        with pytest.raises(ValueError):
            await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=minutes)
        assert not hass.services.calls
    asyncio.run(scenario())


def test_concurrent_extensions_restart_replay_and_old_deadline(storage_module):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        await control.async_pause_camera(hass, storage, 'front', duration_minutes=30)
        before = await storage.async_get_record('front')
        await asyncio.gather(*[
            control.async_extend_privacy(hass, storage, ['front'], duration_minutes=15, operation_id=f'add-{i}')
            for i in range(2)])
        after = await storage.async_get_record('front')
        assert datetime.fromisoformat(after['ends_at']) - datetime.fromisoformat(before['ends_at']) == timedelta(minutes=30)
        reloaded = storage_module.FrigatePrivacyStorage(hass)
        reloaded._store.saved = deepcopy(storage._store.saved)
        await reloaded.async_load()
        calls = list(hass.services.calls)
        replay = await control.async_extend_privacy(hass, reloaded, ['front'], duration_minutes=15, operation_id='add-0')
        assert replay['results'][0]['reason'] == 'stale_operation'
        automatic = await control.async_resume_camera(hass, reloaded, 'front', authority=control.ResumeAuthority.DEADLINE)
        assert automatic['reason'] == 'deadline_not_due'
        assert hass.services.calls == calls
        assert (await reloaded.async_get_record('front'))['ends_at'] == after['ends_at']
    asyncio.run(scenario())


def test_save_failure_never_publishes_extension_and_retry_fails_closed(storage_module):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        await control.async_pause_camera(hass, storage, 'front', duration_minutes=30)
        before = await storage.async_get_record('front')
        calls = list(hass.services.calls)
        original = storage._store.async_save
        async def fail_extension(data):
            if data['paused']['front']['ends_at'] != before['ends_at']:
                raise storage_module.StorageWriteError('synthetic deadline save failure')
            await original(data)
        storage._store.async_save = fail_extension
        with pytest.raises(storage_module.StorageWriteError):
            await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=15, operation_id='save-failure')
        assert (await storage.async_get_record('front'))['ends_at'] == before['ends_at']
        storage._store.async_save = original
        result = await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=15, operation_id='save-failure')
        assert result['results'][0]['reason'] == 'operation_history_expired'
        assert hass.services.calls == calls
    asyncio.run(scenario())


def test_inactive_request_cannot_apply_to_a_later_pause(storage_module):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        initial = await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=15, operation_id='too-early')
        assert initial['results'][0]['reason'] == 'privacy_inactive'
        await control.async_pause_camera(hass, storage, 'front', duration_minutes=30)
        deadline = (await storage.async_get_record('front'))['ends_at']
        retry = await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=15, operation_id='too-early')
        assert retry['results'][0]['reason'] == 'operation_history_expired'
        assert (await storage.async_get_record('front'))['ends_at'] == deadline
    asyncio.run(scenario())


def test_partial_extension_preserves_partial_status_without_retrying_targets(storage_module):
    async def scenario():
        hass = _Hass()
        storage = storage_module.FrigatePrivacyStorage(hass)
        await storage.async_load()
        await control.async_pause_camera(hass, storage, 'front', duration_minutes=30)
        await storage.async_transition_paused('front', 'partial', failed=['switch.front_detect'])
        before = await storage.async_get_record('front')
        calls = list(hass.services.calls)
        result = await control.async_extend_privacy(hass, storage, ['front'], duration_minutes=15)
        assert not result['ok'] and result['phase'] == 'partial'
        assert result['results'][0]['extended'] is True
        assert result['results'][0]['phase'] == 'partial'
        after = await storage.async_get_record('front')
        assert after['failed'] == before['failed']
        assert (await storage.async_get_state())['last_outcome'] == 'partial'
        assert hass.services.calls == calls
    asyncio.run(scenario())
