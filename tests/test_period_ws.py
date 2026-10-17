"""Call the actual read handler under synthetic authorization and unload races."""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from functools import wraps
import pytest

PKG=Path(__file__).resolve().parents[1]/'custom_components/ha_frigate_privacy'

@pytest.fixture
def ws(monkeypatch):
    vol=types.ModuleType('voluptuous')
    vol.Required=vol.Optional=lambda key,**kw:key
    vol.All=vol.Any=lambda *args:object
    vol.Length=vol.Range=lambda **kw:object
    vol.In=lambda *args:object
    vol.Coerce=lambda *args:object
    monkeypatch.setitem(sys.modules,'voluptuous',vol)
    ha=types.ModuleType('homeassistant');ha.__path__=[]
    components=types.ModuleType('homeassistant.components');components.__path__=[]
    api=types.ModuleType('homeassistant.components.websocket_api')
    api.websocket_command=lambda schema:lambda func:func
    api.async_response=lambda func:func
    api.ActiveConnection=object
    def admin(func):
        @wraps(func)
        async def wrapped(hass,connection,msg):
            if not connection.user.is_admin:
                connection.send_error(msg['id'],'unauthorized','Administrator required');return
            return await func(hass,connection,msg)
        return wrapped
    api.require_admin=admin
    components.websocket_api=api
    core=types.ModuleType('homeassistant.core');core.HomeAssistant=object
    for name,mod in (('homeassistant',ha),('homeassistant.components',components),('homeassistant.components.websocket_api',api),('homeassistant.core',core)):
        monkeypatch.setitem(sys.modules,name,mod)
    package=types.ModuleType('period_ws_test');package.__path__=[str(PKG)]
    monkeypatch.setitem(sys.modules,'period_ws_test',package)
    spec=importlib.util.spec_from_file_location('period_ws_test.const',PKG/'const.py')
    constants=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,spec.name,constants);spec.loader.exec_module(constants)
    for name in ('control','storage','replay'):
        mod=types.ModuleType('period_ws_test.'+name)
        if name=='control':
            def forbidden(*a,**kw):raise AssertionError('history must not discover/control cameras')
            mod.async_extend_privacy=mod.async_pause_cameras=mod.async_resume_cameras=mod.discover_frigate_cameras=forbidden
        elif name=='storage':
            mod.FrigatePrivacyStorage=object
            mod.ReplayIntegrityError=type('ReplayIntegrityError',(Exception,),{})
            mod.StorageWriteError=type('StorageWriteError',(Exception,),{})
        else:mod.ReplayFilterSaturatedError=type('ReplayFilterSaturatedError',(Exception,),{})
        monkeypatch.setitem(sys.modules,mod.__name__,mod)
    spec=importlib.util.spec_from_file_location('period_ws_test.websocket_api',PKG/'websocket_api.py')
    module=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,spec.name,module);spec.loader.exec_module(module)
    return module

class Connection:
    def __init__(self):
        self.user=types.SimpleNamespace(id='admin',is_admin=True,is_active=True)
        self.results=[];self.errors=[]
    def send_result(self,*args):self.results.append(args)
    def send_error(self,*args):self.errors.append(args)


def test_repeat_read_no_control_save_and_pre_auth(ws):
    async def scenario():
        class Storage:
            async def async_get_periods(self,**kwargs):return {'status':'ready','periods':[]}
        storage=Storage();hass=types.SimpleNamespace(data={'ha_frigate_privacy':{'storage':storage}})
        connection=Connection()
        for _ in range(2):await ws._ws_get_periods(hass,connection,{'id':1,'days':30})
        assert len(connection.results)==2
        connection.user.is_admin=False
        await ws._ws_get_periods(hass,connection,{'id':2,'days':30})
        assert len(connection.results)==2 and connection.errors[-1][1]=='unauthorized'
    asyncio.run(scenario())

@pytest.mark.parametrize('change',['role','inactive','unload','replace'])
def test_post_await_authority_and_instance_rechecked(ws,change):
    async def scenario():
        entered=asyncio.Event();release=asyncio.Event()
        class Storage:
            async def async_get_periods(self,**kwargs):
                entered.set();await release.wait();return {'periods':[{'camera_id':'private'}]}
        storage=Storage();hass=types.SimpleNamespace(data={'ha_frigate_privacy':{'storage':storage}});connection=Connection()
        task=asyncio.create_task(ws._ws_get_periods(hass,connection,{'id':1,'days':30}))
        await entered.wait()
        if change=='role':connection.user.is_admin=False
        if change=='inactive':connection.user.is_active=False
        if change=='unload':hass.data['ha_frigate_privacy'].pop('storage')
        if change=='replace':hass.data['ha_frigate_privacy']['storage']=Storage()
        release.set();await task
        assert connection.results==[] and connection.errors
    asyncio.run(scenario())
