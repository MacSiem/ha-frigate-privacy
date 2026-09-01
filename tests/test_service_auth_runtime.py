"""Runtime authorization and recovery-gate checks for HA services."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "ha_frigate_privacy"


def _load_init():
    if "voluptuous" not in sys.modules:
        vol = types.ModuleType("voluptuous")
        vol.Required = lambda key, **_kwargs: key
        vol.Optional = lambda key, **_kwargs: key
        vol.Schema = lambda value: value
        vol.Any = lambda *values: values[0] if values else object
        vol.All = lambda *values: values[0] if values else object
        vol.Length = lambda **_kwargs: object
        vol.Coerce = lambda value: value
        vol.Range = lambda **_kwargs: object
        vol.In = lambda values: values
        sys.modules["voluptuous"] = vol
    components = sys.modules.setdefault(
        "homeassistant.components", types.ModuleType("homeassistant.components")
    )
    components.__path__ = getattr(components, "__path__", [])
    frontend = sys.modules.setdefault(
        "homeassistant.components.frontend",
        types.ModuleType("homeassistant.components.frontend"),
    )
    frontend.add_extra_js_url = lambda *_args, **_kwargs: None
    http = sys.modules.setdefault(
        "homeassistant.components.http",
        types.ModuleType("homeassistant.components.http"),
    )
    http.StaticPathConfig = getattr(http, "StaticPathConfig", object)
    config_entries = sys.modules.setdefault(
        "homeassistant.config_entries",
        types.ModuleType("homeassistant.config_entries"),
    )
    config_entries.ConfigEntry = getattr(config_entries, "ConfigEntry", object)
    ha_const = sys.modules.setdefault(
        "homeassistant.const", types.ModuleType("homeassistant.const")
    )
    ha_const.Platform = types.SimpleNamespace(BINARY_SENSOR="binary_sensor")
    core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )
    core.HomeAssistant = getattr(core, "HomeAssistant", object)
    core.ServiceCall = getattr(core, "ServiceCall", object)
    exceptions = sys.modules.setdefault(
        "homeassistant.exceptions",
        types.ModuleType("homeassistant.exceptions"),
    )

    class Unauthorized(Exception):
        pass

    class HomeAssistantError(Exception):
        pass

    exceptions.Unauthorized = Unauthorized
    exceptions.HomeAssistantError = HomeAssistantError

    package = types.ModuleType("fpr_service_auth")
    package.__path__ = [str(PKG)]
    sys.modules["fpr_service_auth"] = package

    const_spec = importlib.util.spec_from_file_location(
        "fpr_service_auth.const", PKG / "const.py"
    )
    const_module = importlib.util.module_from_spec(const_spec)
    sys.modules["fpr_service_auth.const"] = const_module
    assert const_spec and const_spec.loader
    const_spec.loader.exec_module(const_module)

    calls = []
    control = types.ModuleType("fpr_service_auth.control")

    async def pause(*args, **kwargs):
        calls.append(("pause", args, kwargs))

    async def resume(*args, **kwargs):
        calls.append(("resume", args, kwargs))

    control.async_pause_cameras = pause
    control.async_resume_cameras = resume
    sys.modules["fpr_service_auth.control"] = control

    scheduler = types.ModuleType("fpr_service_auth.scheduler")
    scheduler.FrigatePrivacyScheduler = object
    sys.modules["fpr_service_auth.scheduler"] = scheduler
    storage = types.ModuleType("fpr_service_auth.storage")
    storage.FrigatePrivacyStorage = object
    sys.modules["fpr_service_auth.storage"] = storage
    websocket = types.ModuleType("fpr_service_auth.websocket_api")
    websocket.async_register_commands = lambda *_args, **_kwargs: None
    sys.modules["fpr_service_auth.websocket_api"] = websocket

    spec = importlib.util.spec_from_file_location(
        "fpr_service_auth.__init__", PKG / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["fpr_service_auth.__init__"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module, const_module, calls, Unauthorized, HomeAssistantError


init_module, const_module, control_calls, Unauthorized, HomeAssistantError = (
    _load_init()
)


class _Services:
    def __init__(self):
        self.handlers = {}

    def async_register(self, domain, service, handler, **_kwargs):
        self.handlers[(domain, service)] = handler


class _Auth:
    def __init__(self, users):
        self.users = users

    async def async_get_user(self, user_id):
        return self.users.get(user_id)


class _Hass:
    def __init__(self, *, ready, users):
        self.data = {
            const_module.DOMAIN: {
                const_module.DATA_STORAGE: object(),
                const_module.DATA_RECOVERY_READY: ready,
            }
        }
        self.services = _Services()
        self.auth = _Auth(users)


def _call(user_id, **data):
    return types.SimpleNamespace(
        data=data,
        context=types.SimpleNamespace(user_id=user_id),
    )


def test_service_denies_non_admin_and_recovery_pending_before_side_effects():
    async def scenario():
        control_calls.clear()
        users = {
            "member": types.SimpleNamespace(is_admin=False),
            "admin": types.SimpleNamespace(is_admin=True),
        }
        hass = _Hass(ready=False, users=users)
        init_module._async_register_services(hass)
        pause = hass.services.handlers[
            (const_module.DOMAIN, const_module.SERVICE_PAUSE_CAMERA)
        ]

        for call, expected in (
            (_call("member", camera="front"), Unauthorized),
            (_call(None, camera="front"), Unauthorized),
            (_call("admin", camera="front"), HomeAssistantError),
        ):
            try:
                await pause(call)
            except expected:
                pass
            else:
                raise AssertionError(f"{expected.__name__} was not raised")
        return hass

    asyncio.run(scenario())
    assert control_calls == []


def test_authorized_service_propagates_context_and_operation_id():
    async def scenario():
        control_calls.clear()
        hass = _Hass(
            ready=True,
            users={"admin": types.SimpleNamespace(is_admin=True)},
        )
        init_module._async_register_services(hass)
        pause = hass.services.handlers[
            (const_module.DOMAIN, const_module.SERVICE_PAUSE_CAMERA)
        ]
        call = _call(
            "admin",
            camera="front",
            stream_type="all",
            operation_id="pause-service-1",
        )
        await pause(call)
        return call

    call = asyncio.run(scenario())

    assert len(control_calls) == 1
    action, _args, kwargs = control_calls[0]
    assert action == "pause"
    assert kwargs["context"] is call.context
    assert kwargs["operation_id"] == "pause-service-1"
    assert kwargs["source"] == "manual"
