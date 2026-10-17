"""Extension websocket uses the existing admin and recovery boundaries."""
import asyncio
import types
from test_period_ws import Connection, ws


def test_extend_ws_checks_authority_recovery_and_returns_durable_state(ws):
    async def scenario():
        calls = []
        async def extend(*args, **kwargs):
            calls.append((args, kwargs))
            return {'ok':True, 'phase':'paused', 'results':[{'camera_id':'front', 'extended':True, 'phase':'paused', 'ends_at':'2030-01-01T12:45:00+00:00'}]}
        async def get_state():
            return {'paused':{'front':{'ends_at':'2030-01-01T12:45:00+00:00'}}}
        ws.async_extend_privacy = extend
        storage = types.SimpleNamespace(async_get_state=get_state)
        hass = types.SimpleNamespace(data={'ha_frigate_privacy':{'storage':storage, 'recovery_ready':False}})
        conn = Connection(); context = object(); conn.context = lambda msg:context
        msg = {'id':1, 'camera_entity_id':'camera.front', 'duration_minutes':15, 'operation_id':'ws-extension'}
        conn.user.is_admin = False
        await ws._ws_extend_privacy(hass, conn, msg)
        assert conn.errors[-1][1] == 'unauthorized' and not calls
        conn.user.is_admin = True
        await ws._ws_extend_privacy(hass, conn, msg)
        assert conn.errors[-1][1] == 'recovery_pending' and not calls
        hass.data['ha_frigate_privacy']['recovery_ready'] = True
        await ws._ws_extend_privacy(hass, conn, msg)
        assert calls[-1][0][2] == ['camera.front']
        assert calls[-1][1]['context'] is context
        assert calls[-1][1]['operation_id'] == 'ws-extension'
        response = conn.results[-1][1]
        assert response['results'][0]['extended'] is True
        assert response['state']['paused']['front']['ends_at'] == response['results'][0]['ends_at']
    asyncio.run(scenario())
