"""binary_sensor picks up cameras that appear after setup (re-discovery).

A one-shot discovery at setup misses cameras whose switch.<cam>_detect
entities are created later (Frigate booting after HA, or a camera added).
This loads binary_sensor.py with minimal homeassistant stubs and checks the
state-bus listener adds the missing sensor exactly once.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "ha_frigate_privacy"


def _load():
    # --- stub homeassistant surface used by binary_sensor.py + control.py ---
    ha = types.ModuleType("homeassistant")
    comp = types.ModuleType("homeassistant.components")
    bs = types.ModuleType("homeassistant.components.binary_sensor")
    bs.BinarySensorEntity = type("BinarySensorEntity", (), {})
    ce = types.ModuleType("homeassistant.config_entries")
    ce.ConfigEntry = object
    const = types.ModuleType("homeassistant.const")
    const.EVENT_STATE_CHANGED = "state_changed"
    core = types.ModuleType("homeassistant.core")

    def callback(fn):
        return fn

    core.callback = callback
    core.Event = object
    core.HomeAssistant = object
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # mark as package so submodule imports resolve
    ep = types.ModuleType("homeassistant.helpers.entity_platform")
    ep.AddEntitiesCallback = object
    storage_h = types.ModuleType("homeassistant.helpers.storage")

    class _Store:
        def __init__(self, *a, **k):
            self._d = None

        async def async_load(self):
            return self._d

        async def async_save(self, data):
            self._d = data

    storage_h.Store = _Store
    for n, m in {
        "homeassistant": ha,
        "homeassistant.components": comp,
        "homeassistant.components.binary_sensor": bs,
        "homeassistant.config_entries": ce,
        "homeassistant.const": const,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_platform": ep,
        "homeassistant.helpers.storage": storage_h,
    }.items():
        sys.modules.setdefault(n, m)

    pkg = types.ModuleType("fp")
    pkg.__path__ = [str(PKG)]
    sys.modules["fp"] = pkg
    for name in ("const", "control", "storage", "failsafe"):
        spec = importlib.util.spec_from_file_location(f"fp.{name}", PKG / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"fp.{name}"] = mod
        spec.loader.exec_module(mod)
    spec = importlib.util.spec_from_file_location("fp.binary_sensor", PKG / "binary_sensor.py")
    bsmod = importlib.util.module_from_spec(spec)
    sys.modules["fp.binary_sensor"] = bsmod
    spec.loader.exec_module(bsmod)
    return bsmod


binary_sensor = _load()


class _States:
    def __init__(self):
        self._ids = []

    def async_entity_ids(self, domain=None):
        if domain:
            return [e for e in self._ids if e.startswith(domain + ".")]
        return list(self._ids)

    def get(self, entity_id):
        return None  # no camera.* entities -> names fall back to title-cased id

    def add(self, entity_id):
        self._ids.append(entity_id)


class _Bus:
    def __init__(self):
        self._listeners = []

    def async_listen(self, event_type, cb):
        self._listeners.append((event_type, cb))
        return lambda: None

    def fire(self, event_type, data):
        for et, cb in self._listeners:
            if et == event_type:
                cb(types.SimpleNamespace(data=data))


class _Entry:
    def __init__(self):
        self._unloads = []

    def async_on_unload(self, fn):
        self._unloads.append(fn)


class _Storage:
    async def async_get_paused(self, camera_id):
        return {} if camera_id is None else None


class LateCameraDiscoveryTest(unittest.TestCase):
    def test_adds_sensor_for_camera_added_after_setup(self):
        async def scenario():
            hass = types.SimpleNamespace()
            hass.states = _States()
            hass.bus = _Bus()
            hass.data = {binary_sensor.DOMAIN: {}}
            # one camera exists at setup
            hass.states.add("switch.front_door_detect")
            hass.states.add("switch.front_door_recordings")
            hass.data[binary_sensor.DOMAIN][binary_sensor.DATA_STORAGE] = _Storage()

            added = []

            def add_entities(entities, update=False):
                added.extend(entities)

            entry = _Entry()
            await binary_sensor.async_setup_entry(hass, entry, add_entities)
            first = {e._camera_id for e in added}

            # a new camera's switch appears later
            hass.states.add("switch.garage_detect")
            hass.bus.fire("state_changed", {
                "entity_id": "switch.garage_detect",
                "new_state": object(),
            })
            # firing again for the same camera must not duplicate
            hass.bus.fire("state_changed", {
                "entity_id": "switch.garage_recordings",
                "new_state": object(),
            })
            # an unrelated switch must be ignored
            hass.bus.fire("state_changed", {
                "entity_id": "switch.kitchen_light",
                "new_state": object(),
            })
            return first, [e._camera_id for e in added]

        first, all_ids = asyncio.run(scenario())
        self.assertIn("front_door", first)
        self.assertNotIn("garage", first)
        self.assertEqual(all_ids.count("garage"), 1, f"garage added exactly once: {all_ids}")
        self.assertNotIn("kitchen", all_ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
