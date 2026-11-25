"""Individual manual scopes must not stop the Frigate camera unless requested."""
import asyncio

import pytest

from test_restart_recovery import control, _Hass, _Storage


@pytest.mark.parametrize("scope", [
    "all", "main", "sub", "recordings", "snapshots", "detect", "motion",
    "audio_detection", "review_alerts", "review_detections", "camera",
])
def test_only_all_and_camera_scope_stop_camera(scope):
    async def run():
        hass, storage = _Hass(), _Storage()
        await control.async_pause_camera(hass, storage, "front", stream_type=scope)
        stops = [call for call in hass.services.calls if call[:2] == ("camera", "turn_off")]
        assert stops == ([('camera', 'turn_off', 'camera.front')] if scope in {'all', 'camera'} else [])
    asyncio.run(run())
