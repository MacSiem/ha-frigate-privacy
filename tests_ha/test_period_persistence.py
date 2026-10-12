"""Native HA Store fixture: owner must provide an SSD --basetemp directory."""
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from custom_components.ha_frigate_privacy.storage import FrigatePrivacyStorage, StorageWriteError
from custom_components.ha_frigate_privacy.const import STORAGE_KEY
from homeassistant.core import CoreState

pytestmark = pytest.mark.asyncio

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
    hass.state = CoreState.stopping
    with pytest.raises(StorageWriteError):
        await restarted_wrapper.async_transition_paused('synthetic_front','partial')
    assert path.read_bytes() == before
    hass.state = CoreState.not_running
