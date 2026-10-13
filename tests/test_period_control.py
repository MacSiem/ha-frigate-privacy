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
