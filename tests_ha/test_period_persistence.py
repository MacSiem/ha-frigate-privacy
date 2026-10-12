"""Native HA Store fixture: owner must provide an SSD --basetemp directory."""
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from unittest.mock import patch
from custom_components.ha_frigate_privacy.storage import FrigatePrivacyStorage, StorageWriteError
from custom_components.ha_frigate_privacy.const import STORAGE_KEY
from homeassistant.core import CoreState

pytestmark = pytest.mark.asyncio


@pytest.fixture
def hass_storage():
    # Preserve native auth/registry mocks; only this component uses actual disk IO.
    from homeassistant.helpers.storage import Store as HAStore
    from pytest_homeassistant_custom_component.common import mock_storage
    actual_write, actual_load = HAStore._async_write_data, HAStore._async_load
    with mock_storage() as data:
        mocked_write, mocked_load = HAStore._async_write_data, HAStore._async_load
        async def selected_write(store, *arguments):
            if store.key == STORAGE_KEY:
                await actual_write(store, *arguments)
            else:
                await mocked_write(store, *arguments)
        async def selected_load(store):
            if store.key == STORAGE_KEY:
                return await actual_load(store)
            return await mocked_load(store)
        with patch.object(HAStore, '_async_write_data', new=selected_write), patch.object(HAStore, '_async_load', new=selected_load):
            yield data

async def test_ssd_native_atomic_period_store_reloads_from_file(hass, tmp_path):
    if not tmp_path.resolve().is_relative_to(Path('/Volumes/Samsung_SSD')):
        pytest.skip('Native storage fixture requires explicit SSD --basetemp')
    hass.config.config_dir = str(tmp_path)
    storage = FrigatePrivacyStorage(hass)
    await storage.async_load()
    await storage.async_set_paused('synthetic_front', {
        'phase':'pausing', 'started_at':datetime.now(timezone.utc).isoformat(),
        'generation':1, 'period_generation':1,
        'target_outcomes':{'switch.synthetic_front_detect':'pending'},
    })
    path = tmp_path / '.storage' / STORAGE_KEY
    envelope = json.loads(path.read_text())
    assert envelope['data']['privacy_periods']['schema'] == 1
    assert len(envelope['data']['privacy_periods']['periods']) == 1
    restarted_wrapper = FrigatePrivacyStorage(hass)
    await restarted_wrapper.async_load()
    assert (await restarted_wrapper.async_get_periods())['periods'] == (await storage.async_get_periods())['periods']
    before = path.read_bytes()
    await restarted_wrapper.async_get_periods(days=7)
    assert path.read_bytes() == before
    old_state = hass.state
    hass.state = CoreState.stopping
    with pytest.raises(StorageWriteError):
        await restarted_wrapper.async_transition_paused('synthetic_front','partial')
    assert path.read_bytes() == before
    hass.state = old_state


async def test_native_failed_io_rolls_back_periods_and_control(hass, tmp_path):
    if not tmp_path.resolve().is_relative_to(Path('/Volumes/Samsung_SSD')):
        pytest.skip('Native storage fixture requires explicit SSD --basetemp')
    from homeassistant.util.file import WriteError
    hass.config.config_dir = str(tmp_path)
    storage = FrigatePrivacyStorage(hass)
    await storage.async_load()
    await storage.async_set_paused('synthetic_front', {'phase':'paused', 'started_at':datetime.now(timezone.utc).isoformat(), 'generation':1})
    before = (tmp_path / '.storage' / STORAGE_KEY).read_bytes()
    old = await storage.async_get_periods()
    with patch.object(storage._store, '_async_write_data', side_effect=WriteError('synthetic')):
        with pytest.raises(StorageWriteError):
            await storage.async_transition_paused('synthetic_front','partial')
    assert (tmp_path / '.storage' / STORAGE_KEY).read_bytes() == before
    assert (await storage.async_get_periods())['periods'] == old['periods']
    assert (await storage.async_get_record('synthetic_front'))['phase'] == 'paused'
