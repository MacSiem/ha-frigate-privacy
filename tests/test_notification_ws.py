"""Notification boundaries under synthetic session and unload races."""
import asyncio
from types import SimpleNamespace
import pytest
from test_period_ws import Connection, ws  # reuse lightweight actual-handler loader

DOMAIN = 'ha_frigate_privacy'


def connection():
    result = Connection()
    result.user.system_generated = False
    result.context = lambda msg: SimpleNamespace(user_id=result.user.id)
    return result


@pytest.mark.parametrize('status', ['ha_accepted', 'error', 'no_channel'])
def test_test_notification_returns_fixed_outcome_without_other_actions(ws, status):
    async def scenario():
        calls = []
        class Notifier:
            async def async_test(self):
                calls.append(True)
                return {'status': status}
        # No storage, camera control, config writer or bus exists in this fixture.
        hass = SimpleNamespace(data={DOMAIN: {'notifications': Notifier()}})
        conn = connection()
        await ws._ws_test_notification(hass, conn, {'id': 1})
        assert calls == [True]
        assert conn.results == [(1, {'status': status})]
        assert not conn.errors
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['role', 'inactive', 'system', 'no_context'])
def test_test_notification_rejects_before_side_effect(ws, change):
    async def scenario():
        class Notifier:
            async def async_test(self):
                raise AssertionError('unauthorized request reached delivery')
        conn = connection()
        if change == 'role': conn.user.is_admin = False
        if change == 'inactive': conn.user.is_active = False
        if change == 'system': conn.user.system_generated = True
        if change == 'no_context': conn.context = lambda msg: SimpleNamespace(user_id=None)
        await ws._ws_test_notification(SimpleNamespace(data={DOMAIN: {'notifications': Notifier()}}), conn, {'id': 1})
        assert not conn.results and conn.errors[-1][1] == 'unauthorized'
    asyncio.run(scenario())


@pytest.mark.parametrize('handler', ['_ws_test_notification', '_ws_get_state'])
@pytest.mark.parametrize('change', ['role', 'inactive', 'identity', 'same_object_identity', 'unload', 'replace'])
def test_private_response_rechecks_session_and_notifier(ws, handler, change):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def wait():
            entered.set()
            await release.wait()
            return {'status': 'ha_accepted'} if handler.endswith('notification') else {'private': 'state'}
        notifier = SimpleNamespace(async_test=wait, snapshot=lambda: {'destination': 'private-phone'})
        storage = SimpleNamespace(async_get_state=wait)
        hass = SimpleNamespace(data={DOMAIN: {'notifications': notifier, 'storage': storage}})
        ws.discover_frigate_cameras = lambda hass: []
        conn = connection()
        task = asyncio.create_task(getattr(ws, handler)(hass, conn, {'id': 1}))
        await asyncio.wait_for(entered.wait(), 1)
        if change == 'role': conn.user.is_admin = False
        if change == 'inactive': conn.user.is_active = False
        if change == 'identity': conn.user = SimpleNamespace(id='other', is_admin=True, is_active=True)
        if change == 'same_object_identity': conn.user.id = 'other'
        if change == 'unload': hass.data[DOMAIN].pop('notifications')
        if change == 'replace': hass.data[DOMAIN]['notifications'] = object()
        release.set()
        await task
        assert not conn.results and conn.errors
        assert 'private' not in str(conn.errors)
    asyncio.run(scenario())


def test_get_state_reads_latest_snapshot_after_storage_wait_without_mutating_storage(ws):
    async def scenario():
        state = {'records': {}}
        snapshot = {'destination': 'notify.saved', 'label': 'Saved', 'available': True,
                    'events': {'errors': True, 'paused': False, 'resumed': False, 'scheduled': False}}
        async def read(): return state
        notifier = SimpleNamespace(snapshot=lambda: snapshot)
        hass = SimpleNamespace(data={DOMAIN: {'storage': SimpleNamespace(async_get_state=read), 'notifications': notifier}})
        ws.discover_frigate_cameras = lambda hass: []
        conn = connection()
        await ws._ws_get_state(hass, conn, {'id': 1})
        assert conn.results[0][1]['notifications'] == snapshot
        assert 'notifications' not in state
    asyncio.run(scenario())


def test_test_notification_exception_is_safe_and_cancellation_unconfirmed(ws):
    async def scenario():
        async def failed(): raise RuntimeError('private-token-and-phone')
        notifier = SimpleNamespace(async_test=failed)
        hass = SimpleNamespace(data={DOMAIN: {'notifications': notifier}})
        conn = connection()
        await ws._ws_test_notification(hass, conn, {'id': 1})
        assert conn.results == [(1, {'status': 'error'})]
        entered = asyncio.Event()
        async def waiting():
            entered.set()
            await asyncio.Event().wait()
        notifier.async_test = waiting
        conn = connection()
        task = asyncio.create_task(ws._ws_test_notification(hass, conn, {'id': 2}))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert not conn.results
    asyncio.run(scenario())
