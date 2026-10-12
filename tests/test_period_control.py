"""Actual control path + actual storage producer, using existing HA fixtures."""
import asyncio
from test_period_storage import storage_module
from test_restart_recovery import control, _Hass


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
