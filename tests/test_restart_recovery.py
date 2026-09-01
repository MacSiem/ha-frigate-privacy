"""Crash-safe Frigate Privacy state-machine regression tests."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from copy import deepcopy
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "ha_frigate_privacy"


def _load_control():
    homeassistant = sys.modules.setdefault(
        "homeassistant", types.ModuleType("homeassistant")
    )
    homeassistant.__path__ = getattr(homeassistant, "__path__", [])
    core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )
    core.HomeAssistant = getattr(core, "HomeAssistant", object)
    helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    helpers.__path__ = getattr(helpers, "__path__", [])
    homeassistant.helpers = helpers
    entity_registry = sys.modules.setdefault(
        "homeassistant.helpers.entity_registry",
        types.ModuleType("homeassistant.helpers.entity_registry"),
    )
    entity_registry.async_get = lambda hass: hass.entity_registry
    package = types.ModuleType("fpr_recovery")
    package.__path__ = [str(PKG)]
    sys.modules["fpr_recovery"] = package
    for name in ("const", "failsafe"):
        spec = importlib.util.spec_from_file_location(
            f"fpr_recovery.{name}", PKG / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"fpr_recovery.{name}"] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)

    storage_module = types.ModuleType("fpr_recovery.storage")
    storage_module.FrigatePrivacyStorage = object
    sys.modules["fpr_recovery.storage"] = storage_module
    spec = importlib.util.spec_from_file_location(
        "fpr_recovery.control", PKG / "control.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["fpr_recovery.control"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


control = _load_control()


class _State:
    def __init__(self, state: str, name: str | None = None) -> None:
        self.state = state
        self.attributes = {"friendly_name": name} if name else {}


class _States:
    def __init__(self, values: dict[str, _State]) -> None:
        self.values = values

    def get(self, entity_id: str | None):
        return self.values.get(entity_id)

    def async_entity_ids(self, domain: str | None = None):
        ids = list(self.values)
        return [item for item in ids if item.startswith(f"{domain}.")] if domain else ids


class _RegistryEntry:
    def __init__(self, platform: str) -> None:
        self.platform = platform


class _Registry:
    def __init__(self, platforms: dict[str, str]) -> None:
        self.platforms = platforms

    def async_get(self, entity_id: str):
        platform = self.platforms.get(entity_id)
        return _RegistryEntry(platform) if platform else None


class _Services:
    def __init__(self, states: _States) -> None:
        self.states = states
        self.calls: list[tuple[str, str, str]] = []
        self.fail_on: set[tuple[str, str, str]] = set()
        self.cancel_after_apply: set[tuple[str, str, str]] = set()
        self.update_state = True
        self.contexts = []

    async def async_call(self, domain, service, data, *, blocking=False, context=None, **_kwargs):
        entity_id = data.get("entity_id", "")
        call = (domain, service, entity_id)
        self.calls.append(call)
        self.contexts.append(context)
        await asyncio.sleep(0)
        if call in self.fail_on:
            raise RuntimeError("fixture service failure")
        if self.update_state and entity_id in self.states.values and service in {"turn_on", "turn_off"}:
            if domain == "camera" and service == "turn_on":
                # Home Assistant camera entities report idle/streaming/recording
                # while enabled, not the generic switch state "on".
                self.states.values[entity_id].state = "idle"
            else:
                self.states.values[entity_id].state = "on" if service == "turn_on" else "off"
        if call in self.cancel_after_apply:
            self.cancel_after_apply.remove(call)
            raise asyncio.CancelledError


class _Bus:
    def __init__(self) -> None:
        self.events = []

    def async_fire(self, event_type, data):
        self.events.append((event_type, deepcopy(data)))


class _Hass:
    def __init__(self) -> None:
        values = {
            "camera.front": _State("streaming", "Front"),
            "switch.front_detect": _State("on"),
            "switch.front_recordings": _State("on"),
        }
        self.states = _States(values)
        self.entity_registry = _Registry({entity_id: "frigate" for entity_id in values})
        self.services = _Services(self.states)
        self.bus = _Bus()


class _Storage:
    def __init__(self, paused: dict[str, dict] | None = None) -> None:
        self.paused = deepcopy(paused or {})
        self.transitions: list[tuple[str, str]] = []
        self.fail_initial_save = False
        self.fail_transition = False
        self.fail_active_transition_once = False
        self.seen_operations: set[tuple[str, str, str]] = set()

    async def async_reserve_camera_operation(
        self, camera_id, action, operation_id, *, history=None
    ):
        for item in history or []:
            if isinstance(item, dict) and item.get("id") and item.get("action"):
                self.seen_operations.add(
                    (camera_id, str(item["action"]), str(item["id"]))
                )
        key = (camera_id, action, operation_id)
        if key in self.seen_operations:
            return False
        self.seen_operations.add(key)
        return True

    async def async_get_paused(self, camera_id, *, include_inactive=False):
        if camera_id is None:
            records = deepcopy(self.paused)
            if include_inactive:
                return records
            return {
                key: value
                for key, value in records.items()
                if value.get("active", True)
            }
        record = deepcopy(self.paused.get(camera_id))
        if record and not include_inactive and not record.get("active", True):
            return None
        return record

    async def async_get_record(self, camera_id):
        return await self.async_get_paused(camera_id, include_inactive=True)

    async def async_set_paused(self, camera_id, state):
        if self.fail_initial_save:
            raise RuntimeError("fixture initial save failure")
        item = deepcopy(state)
        item["camera_id"] = camera_id
        item["active"] = item.get("phase") != "active"
        self.paused[camera_id] = item
        self.transitions.append((camera_id, item.get("phase")))
        return deepcopy(item)

    async def async_transition_paused(self, camera_id, phase, **updates):
        if phase == "active" and self.fail_active_transition_once:
            self.fail_active_transition_once = False
            raise RuntimeError("fixture terminal save failure")
        if self.fail_transition:
            raise RuntimeError("fixture transition save failure")
        item = self.paused[camera_id]
        item.update(deepcopy(updates))
        item["phase"] = phase
        item["active"] = phase != "active"
        self.transitions.append((camera_id, phase))
        return deepcopy(item)

    async def async_mark_active(self, camera_id, **updates):
        item = await self.async_transition_paused(camera_id, "active", **updates)
        self.paused[camera_id]["active"] = False
        return deepcopy(self.paused[camera_id])

    async def async_clear_paused(self, camera_id):
        self.paused.pop(camera_id, None)
        self.transitions.append((camera_id, "active"))
        return True

    async def async_mark_resume_blocked(self, camera_id, *, reason, failed, unavailable):
        return await self.async_transition_paused(
            camera_id,
            "error",
            reason=reason,
            failed=list(failed),
            unavailable=list(unavailable),
            resume_blocked=True,
        )


def _paused_record(*, phase: str = "paused") -> dict:
    return {
        "camera_id": "front",
        "camera_entity_id": "camera.front",
        "name": "Front",
        "phase": phase,
        "active": True,
        "stream_type": "all",
        "source": "manual",
        "switches": ["switch.front_detect", "switch.front_recordings"],
        "camera_toggled": True,
        "started_at": "2026-08-31T12:00:00+00:00",
        "ends_at": "2026-08-31T12:30:00+00:00",
        "operation_id": "pause-front-1",
    }


def test_pause_persists_intent_before_control_and_reports_verified_phase():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        result = await control.async_pause_camera(
            hass, storage, "front", duration_minutes=30
        )
        return storage, result

    storage, result = asyncio.run(scenario())

    assert storage.transitions[0] == ("front", "pausing")
    assert result["phase"] == "paused"
    assert storage.paused["front"]["phase"] == "paused"
    assert storage.paused["front"]["operation_id"]
    assert storage.paused["front"]["target_outcomes"]["switch.front_detect"] == "paused"
    assert storage.paused["front"]["target_outcomes"]["switch.front_recordings"] == "paused"
    assert storage.paused["front"]["target_outcomes"]["camera.front"] == "paused"
    assert storage.paused["front"]["target_outcomes"]["switch.front_motion"] == "missing"
    assert storage.paused["front"]["last_verified_actual_state"] == {
        "switch.front_detect": "off",
        "switch.front_recordings": "off",
        "camera.front": "off",
    }


def test_partial_pause_is_truthful_and_retains_evidence():
    async def scenario():
        hass = _Hass()
        hass.services.fail_on.add(("switch", "turn_off", "switch.front_recordings"))
        storage = _Storage()
        result = await control.async_pause_camera(hass, storage, "front")
        return storage, result

    storage, result = asyncio.run(scenario())

    assert result["phase"] == "partial"
    assert result["paused"] is False
    assert storage.paused["front"]["phase"] == "partial"
    assert storage.paused["front"]["failed"] == ["switch.front_recordings"]


def test_unknown_camera_is_rejected_before_any_service_call():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        result = await control.async_pause_camera(hass, storage, "not_discovered")
        return hass, storage, result

    hass, storage, result = asyncio.run(scenario())

    assert result["phase"] == "error"
    assert result["reason"] == "camera_not_discovered"
    assert hass.services.calls == []
    assert storage.paused == {}


def test_suffix_collision_from_foreign_platform_is_not_discovered_or_toggled():
    async def scenario():
        hass = _Hass()
        hass.states.values["switch.garage_detect"] = _State("on")
        hass.states.values["switch.garage_recordings"] = _State("on")
        hass.states.values["camera.garage"] = _State("streaming", "Garage")
        hass.entity_registry.platforms.update(
            {
                "switch.garage_detect": "unrelated_platform",
                "switch.garage_recordings": "unrelated_platform",
                "camera.garage": "unrelated_platform",
            }
        )
        storage = _Storage()
        discovered = control.discover_frigate_cameras(hass)
        result = await control.async_pause_camera(hass, storage, "garage")
        return hass, storage, discovered, result

    hass, storage, discovered, result = asyncio.run(scenario())

    assert {item["camera_id"] for item in discovered} == {"front"}
    assert result["reason"] == "camera_not_discovered"
    assert hass.services.calls == []
    assert storage.paused == {}


def test_duplicate_concurrent_resume_executes_each_target_once():
    async def scenario():
        hass = _Hass()
        for state in hass.states.values.values():
            state.state = "off"
        storage = _Storage({"front": _paused_record()})
        first, second = await asyncio.gather(
            control.async_resume_camera(hass, storage, "front"),
            control.async_resume_camera(hass, storage, "front"),
        )
        return hass, storage, first, second

    hass, storage, first, second = asyncio.run(scenario())

    mutating_calls = [
        call for call in hass.services.calls if call[0] in {"camera", "switch"}
    ]
    assert mutating_calls.count(("camera", "turn_on", "camera.front")) == 1
    assert mutating_calls.count(("switch", "turn_on", "switch.front_detect")) == 1
    assert mutating_calls.count(("switch", "turn_on", "switch.front_recordings")) == 1
    assert {first["phase"], second["phase"]} == {"active"}
    assert storage.transitions.count(("front", "resuming")) >= 1
    assert storage.transitions[-1] == ("front", "active")


def test_restart_resuming_record_recovers_once_and_becomes_active():
    async def scenario():
        hass = _Hass()
        for state in hass.states.values.values():
            state.state = "off"
        storage = _Storage({"front": _paused_record(phase="resuming")})
        result = await control.async_recover_transitions(hass, storage)
        return hass, storage, result

    hass, storage, result = asyncio.run(scenario())

    assert result["recovered"] == ["front"]
    assert storage.paused["front"]["phase"] == "active"
    assert storage.paused["front"]["active"] is False
    assert storage.paused["front"]["last_verified_actual_state"]["camera.front"] == "idle"
    assert hass.services.calls.count(("camera", "turn_on", "camera.front")) == 1


def test_terminal_state_save_failure_repauses_every_reenabled_target():
    async def scenario():
        hass = _Hass()
        for state in hass.states.values.values():
            state.state = "off"
        storage = _Storage({"front": _paused_record()})
        storage.fail_active_transition_once = True
        result = await control.async_resume_camera(hass, storage, "front")
        return hass, storage, result

    hass, storage, result = asyncio.run(scenario())

    assert result["resumed"] is False
    assert result["phase"] == "error"
    assert result["decision"]["reason"] == "state_persistence_failed"
    assert storage.paused["front"]["phase"] == "error"
    assert hass.states.values["camera.front"].state == "off"
    assert hass.states.values["switch.front_detect"].state == "off"
    assert hass.states.values["switch.front_recordings"].state == "off"


def test_resume_cancellation_repauses_every_observed_target_before_propagating():
    async def scenario(cancel_call, *, cancel_cleanup_call=None):
        hass = _Hass()
        for state in hass.states.values.values():
            state.state = "off"
        hass.services.cancel_after_apply.add(cancel_call)
        if cancel_cleanup_call is not None:
            hass.services.cancel_after_apply.add(cancel_cleanup_call)
        storage = _Storage({"front": _paused_record()})

        try:
            await control.async_resume_camera(hass, storage, "front")
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("resume cancellation must be propagated")
        return hass, storage

    cases = (
        (("camera", "turn_on", "camera.front"), None),
        (("switch", "turn_on", "switch.front_detect"), None),
        (
            ("switch", "turn_on", "switch.front_detect"),
            ("camera", "turn_off", "camera.front"),
        ),
    )
    for cancel_call, cleanup_call in cases:
        hass, storage = asyncio.run(
            scenario(cancel_call, cancel_cleanup_call=cleanup_call)
        )
        assert hass.states.values["camera.front"].state == "off"
        assert hass.states.values["switch.front_detect"].state == "off"
        assert hass.states.values["switch.front_recordings"].state == "off"
        assert storage.paused["front"]["phase"] == "error"
        assert storage.paused["front"]["active"] is True
        assert storage.paused["front"]["resume_blocked"] is True
        assert storage.paused["front"]["reason"] == "resume_cancelled"


def test_resume_failure_stays_error_and_never_claims_active():
    async def scenario():
        hass = _Hass()
        for state in hass.states.values.values():
            state.state = "off"
        hass.services.fail_on.add(("switch", "turn_on", "switch.front_recordings"))
        storage = _Storage({"front": _paused_record()})
        result = await control.async_resume_camera(hass, storage, "front")
        return storage, result

    storage, result = asyncio.run(scenario())

    assert result["resumed"] is False
    assert result["phase"] == "error"
    assert storage.paused["front"]["phase"] == "error"
    assert storage.paused["front"]["active"] is True


def test_resume_only_reenables_targets_recorded_by_pause():
    async def scenario():
        hass = _Hass()
        hass.states.values["switch.front_snapshots"] = _State("off")
        for entity_id in ("camera.front", "switch.front_detect", "switch.front_recordings"):
            hass.states.values[entity_id].state = "off"
        storage = _Storage({"front": _paused_record()})
        result = await control.async_resume_camera(hass, storage, "front")
        return hass, result

    hass, result = asyncio.run(scenario())

    assert result["phase"] == "active"
    assert ("switch", "turn_on", "switch.front_snapshots") not in hass.services.calls
    assert hass.states.values["switch.front_snapshots"].state == "off"


def test_poisoned_persisted_targets_fail_closed_before_side_effects():
    async def scenario():
        hass = _Hass()
        hass.states.values["switch.unrelated"] = _State("off")
        hass.entity_registry.platforms["switch.unrelated"] = "unrelated_platform"
        record = _paused_record()
        record["switches"] = ["switch.front_detect", "switch.unrelated"]
        storage = _Storage({"front": record})
        result = await control.async_resume_camera(hass, storage, "front")
        return hass, storage, result

    hass, storage, result = asyncio.run(scenario())

    assert result["resumed"] is False
    assert result["phase"] == "error"
    assert result["decision"]["reason"] == "invalid_persisted_targets"
    assert hass.services.calls == []
    assert storage.paused["front"]["phase"] == "error"


def test_initial_storage_failure_performs_zero_control_calls():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        storage.fail_initial_save = True
        try:
            await control.async_pause_camera(hass, storage, "front")
        except RuntimeError as error:
            assert "initial save" in str(error)
        else:
            raise AssertionError("storage failure must be surfaced")
        return hass

    hass = asyncio.run(scenario())
    assert hass.services.calls == []


def test_final_pause_save_failure_leaves_recoverable_intent():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        storage.fail_transition = True
        try:
            await control.async_pause_camera(hass, storage, "front")
        except RuntimeError as error:
            assert "transition save" in str(error)
        else:
            raise AssertionError("final storage failure must be surfaced")
        return hass, storage

    hass, storage = asyncio.run(scenario())
    assert storage.paused["front"]["phase"] == "pausing"
    assert ("switch", "turn_off", "switch.front_detect") in hass.services.calls


def test_readback_mismatch_is_partial_and_never_claims_paused():
    async def scenario():
        hass = _Hass()
        hass.services.update_state = False
        storage = _Storage()
        result = await control.async_pause_camera(hass, storage, "front")
        return storage, result

    storage, result = asyncio.run(scenario())
    assert result["paused"] is False
    assert result["phase"] == "partial"
    assert storage.paused["front"]["phase"] == "partial"


def test_pause_replay_preserves_original_exact_target_set():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        first = await control.async_pause_camera(
            hass, storage, "front", operation_id="request-1"
        )
        calls_after_first = list(hass.services.calls)
        second = await control.async_pause_camera(
            hass, storage, "front", operation_id="request-1"
        )
        return hass, storage, first, second, calls_after_first

    hass, storage, first, second, calls_after_first = asyncio.run(scenario())
    assert second["reason"] == "idempotent_replay"
    assert second["switches"] == first["switches"]
    assert storage.paused["front"]["switches"] == first["switches"]
    assert hass.services.calls == calls_after_first


def test_active_schedule_extends_manual_subset_without_losing_exact_targets():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        manual = await control.async_pause_camera(
            hass,
            storage,
            "front",
            stream_type="main",
            duration_minutes=15,
            source="manual",
        )
        scheduled = await control.async_pause_camera(
            hass,
            storage,
            "front",
            stream_type="all",
            source="schedule",
            schedule_id="B",
        )
        return hass, storage, manual, scheduled

    hass, storage, manual, scheduled = asyncio.run(scenario())

    assert manual["switches"] == ["switch.front_recordings"]
    assert scheduled["phase"] == "paused"
    assert storage.paused["front"]["source"] == "manual"
    assert storage.paused["front"]["active_schedule_ids"] == ["B"]
    assert storage.paused["front"]["switches"] == [
        "switch.front_recordings",
        "switch.front_detect",
    ]
    assert storage.paused["front"]["camera_toggled"] is True
    assert hass.states.values["switch.front_detect"].state == "off"
    assert hass.states.values["camera.front"].state == "off"


def test_restart_partial_resume_skips_already_restored_target():
    async def scenario():
        hass = _Hass()
        hass.states.values["camera.front"].state = "idle"
        hass.states.values["switch.front_detect"].state = "on"
        hass.states.values["switch.front_recordings"].state = "off"
        storage = _Storage({"front": _paused_record(phase="resuming")})
        result = await control.async_recover_transitions(hass, storage)
        return hass, result

    hass, result = asyncio.run(scenario())
    assert result["recovered"] == ["front"]
    assert ("camera", "turn_on", "camera.front") not in hass.services.calls
    assert ("switch", "turn_on", "switch.front_detect") not in hass.services.calls
    assert hass.services.calls.count(("switch", "turn_on", "switch.front_recordings")) == 1


def test_failed_restart_resume_repauses_targets_restored_before_restart():
    async def scenario():
        hass = _Hass()
        hass.states.values["camera.front"].state = "idle"
        hass.states.values["switch.front_detect"].state = "on"
        hass.states.values["switch.front_recordings"].state = "off"
        hass.services.fail_on.add(("switch", "turn_on", "switch.front_recordings"))
        storage = _Storage({"front": _paused_record(phase="resuming")})
        result = await control.async_recover_transitions(hass, storage)
        return hass, storage, result

    hass, storage, result = asyncio.run(scenario())

    assert result["held"] == ["front"]
    assert storage.paused["front"]["phase"] == "error"
    assert ("camera", "turn_off", "camera.front") in hass.services.calls
    assert ("switch", "turn_off", "switch.front_detect") in hass.services.calls
    assert hass.states.values["camera.front"].state == "off"
    assert hass.states.values["switch.front_detect"].state == "off"


def test_restart_during_pause_reconstructs_exact_changed_targets():
    async def scenario():
        hass = _Hass()
        for state in hass.states.values.values():
            state.state = "off"
        record = _paused_record(phase="pausing")
        record["planned_switches"] = [
            "switch.front_detect",
            "switch.front_recordings",
        ]
        record["switches"] = []
        record["camera_planned"] = True
        record["camera_toggled"] = False
        storage = _Storage({"front": record})
        recovered = await control.async_recover_transitions(hass, storage)
        partial = deepcopy(storage.paused["front"])
        resumed = await control.async_resume_camera(hass, storage, "front")
        return recovered, partial, resumed

    recovered, partial, resumed = asyncio.run(scenario())
    assert recovered["held"] == ["front"]
    assert partial["phase"] == "partial"
    assert partial["switches"] == [
        "switch.front_detect",
        "switch.front_recordings",
    ]
    assert partial["camera_toggled"] is True
    assert resumed["phase"] == "active"


def test_restart_during_schedule_extension_preserves_original_and_new_targets():
    async def scenario():
        hass = _Hass()
        for state in hass.states.values.values():
            state.state = "off"
        record = _paused_record(phase="pausing")
        record.update(
            {
                "source": "manual",
                "extension": True,
                "extension_base_switches": ["switch.front_recordings"],
                "extension_planned_switches": ["switch.front_detect"],
                "switches": ["switch.front_recordings"],
                "camera_planned": True,
                "camera_toggled": False,
                "active_schedule_ids": ["B"],
            }
        )
        storage = _Storage({"front": record})
        recovered = await control.async_recover_transitions(hass, storage)
        return storage, recovered

    storage, recovered = asyncio.run(scenario())

    assert recovered["held"] == ["front"]
    assert storage.paused["front"]["switches"] == [
        "switch.front_recordings",
        "switch.front_detect",
    ]
    assert storage.paused["front"]["camera_toggled"] is True


def test_request_context_is_propagated_to_control_calls():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        context = types.SimpleNamespace(user_id="admin-user")
        await control.async_pause_camera(hass, storage, "front", context=context)
        return hass, context

    hass, context = asyncio.run(scenario())
    assert hass.services.contexts
    assert all(item is context for item in hass.services.contexts)


def test_scoped_operation_ids_remain_bounded_and_camera_unique():
    parent = "request-" + ("x" * 128)

    front = control._scoped_operation_id(parent, "front")
    back = control._scoped_operation_id(parent, "back")

    assert front != back
    assert len(front) <= 128
    assert len(back) <= 128


def test_delayed_pause_retry_cannot_reverse_a_newer_resume():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        paused = await control.async_pause_camera(
            hass, storage, "front", operation_id="pause-P"
        )
        resumed = await control.async_resume_camera(
            hass, storage, "front", operation_id="resume-R"
        )
        calls_before_retry = list(hass.services.calls)
        delayed = await control.async_pause_camera(
            hass, storage, "front", operation_id="pause-P"
        )
        return hass, paused, resumed, delayed, calls_before_retry

    hass, paused, resumed, delayed, calls_before_retry = asyncio.run(scenario())

    assert paused["phase"] == "paused"
    assert resumed["phase"] == "active"
    assert delayed["reason"] == "stale_operation"
    assert delayed["paused"] is False
    assert hass.services.calls == calls_before_retry


def test_pause_operation_id_rejects_a_different_request_payload():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        first = await control.async_pause_camera(
            hass,
            storage,
            "front",
            stream_type="main",
            duration_minutes=15,
            operation_id="pause-P",
        )
        calls_before_retry = list(hass.services.calls)
        mismatch = await control.async_pause_camera(
            hass,
            storage,
            "front",
            stream_type="all",
            duration_minutes=30,
            operation_id="pause-P",
        )
        return hass, first, mismatch, calls_before_retry

    hass, first, mismatch, calls_before_retry = asyncio.run(scenario())

    assert first["phase"] == "paused"
    assert mismatch["reason"] == "operation_payload_mismatch"
    assert mismatch["paused"] is False
    assert hass.services.calls == calls_before_retry


def test_delayed_resume_retry_cannot_cancel_a_newer_privacy_pause():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        await control.async_pause_camera(
            hass, storage, "front", operation_id="pause-P"
        )
        await control.async_resume_camera(
            hass, storage, "front", operation_id="resume-R"
        )
        latest = await control.async_pause_camera(
            hass, storage, "front", operation_id="pause-Q"
        )
        calls_before_retry = list(hass.services.calls)
        delayed = await control.async_resume_camera(
            hass, storage, "front", operation_id="resume-R"
        )
        return hass, storage, latest, delayed, calls_before_retry

    hass, storage, latest, delayed, calls_before_retry = asyncio.run(scenario())

    assert latest["phase"] == "paused"
    assert delayed["reason"] == "stale_operation"
    assert delayed["resumed"] is False
    assert storage.paused["front"]["phase"] == "paused"
    assert hass.services.calls == calls_before_retry


def test_evicted_resume_retry_cannot_cancel_a_newer_privacy_pause():
    async def scenario():
        hass = _Hass()
        storage = _Storage()
        await control.async_pause_camera(
            hass, storage, "front", operation_id="pause-initial"
        )
        await control.async_resume_camera(
            hass, storage, "front", operation_id="resume-old"
        )
        for index in range(9):
            await control.async_pause_camera(
                hass, storage, "front", operation_id=f"pause-{index}"
            )
            await control.async_resume_camera(
                hass, storage, "front", operation_id=f"resume-{index}"
            )
        latest = await control.async_pause_camera(
            hass, storage, "front", operation_id="pause-latest"
        )
        calls_before_retry = list(hass.services.calls)
        delayed = await control.async_resume_camera(
            hass, storage, "front", operation_id="resume-old"
        )
        return hass, storage, latest, delayed, calls_before_retry

    hass, storage, latest, delayed, calls_before_retry = asyncio.run(scenario())

    assert latest["phase"] == "paused"
    assert delayed["reason"] == "operation_history_expired"
    assert delayed["resumed"] is False
    assert storage.paused["front"]["phase"] == "paused"
    assert hass.services.calls == calls_before_retry


def test_resume_retry_metadata_survives_failure_and_restart_recovery():
    async def scenario():
        hass = _Hass()
        for state in hass.states.values.values():
            state.state = "off"
        hass.services.fail_on.add(
            ("switch", "turn_on", "switch.front_recordings")
        )
        storage = _Storage({"front": _paused_record()})
        failed = await control.async_resume_camera(
            hass, storage, "front", operation_id="resume-R1"
        )

        # Simulate a crash after a new retry persisted its intent but before
        # it completed side effects. Recovery must continue that generation.
        record = storage.paused["front"]
        record["phase"] = "resuming"
        record["resume_operation_id"] = "resume-R2"
        record["generation"] = int(record.get("generation") or 0) + 1
        record["resume_attempt_count"] = 2
        record["last_attempt_operation_id"] = "resume-R2"
        record["operation_history"] = control._upsert_operation(
            control._operation_history(record),
            operation_id="resume-R2",
            action="resume",
            generation=record["generation"],
            result={
                "camera_id": "front",
                "resumed": False,
                "phase": "resuming",
                "operation_id": "resume-R2",
            },
        )
        hass.services.fail_on.clear()
        recovered = await control.async_recover_transitions(hass, storage)
        return storage, failed, recovered

    storage, failed, recovered = asyncio.run(scenario())

    assert failed["phase"] == "error"
    assert recovered["recovered"] == ["front"]
    terminal = storage.paused["front"]
    assert terminal["phase"] == "active"
    assert terminal["resume_attempt_count"] == 3
    assert terminal["last_attempt_operation_id"] == "resume-R2"
    assert terminal["last_attempt_at"]


def test_late_frigate_entities_preserve_planned_targets_until_recovery():
    async def scenario():
        hass = _Hass()
        record = _paused_record(phase="pausing")
        record.update(
            {
                "planned_switches": [
                    "switch.front_detect",
                    "switch.front_recordings",
                ],
                "switches": [],
                "camera_planned": True,
                "camera_toggled": False,
            }
        )
        storage = _Storage({"front": record})
        saved_states = hass.states.values
        saved_platforms = hass.entity_registry.platforms
        hass.states.values = {}
        hass.entity_registry.platforms = {}

        pending = await control.async_recover_transitions(hass, storage)
        before_early_resume = deepcopy(storage.paused["front"])
        early_resume = await control.async_resume_camera(hass, storage, "front")

        hass.states.values = saved_states
        hass.entity_registry.platforms = saved_platforms
        for state in hass.states.values.values():
            state.state = "off"
        recovered = await control.async_recover_transitions(hass, storage)
        partial = deepcopy(storage.paused["front"])
        resumed = await control.async_resume_camera(hass, storage, "front")
        return (
            hass,
            pending,
            before_early_resume,
            early_resume,
            recovered,
            partial,
            resumed,
        )

    (
        hass,
        pending,
        before_early_resume,
        early_resume,
        recovered,
        partial,
        resumed,
    ) = asyncio.run(scenario())

    assert pending["pending"] == ["front"]
    assert before_early_resume["phase"] == "pausing"
    assert before_early_resume["planned_switches"] == [
        "switch.front_detect",
        "switch.front_recordings",
    ]
    assert early_resume["reason"] == "recovery_pending"
    assert recovered["held"] == ["front"]
    assert partial["phase"] == "partial"
    assert partial["switches"] == [
        "switch.front_detect",
        "switch.front_recordings",
    ]
    assert partial["camera_toggled"] is True
    assert resumed["phase"] == "active"
    assert ("camera", "turn_on", "camera.front") in hass.services.calls
    assert ("switch", "turn_on", "switch.front_detect") in hass.services.calls
    assert (
        "switch",
        "turn_on",
        "switch.front_recordings",
    ) in hass.services.calls


def test_permanently_missing_recovery_target_does_not_block_healthy_camera():
    async def scenario():
        hass = _Hass()
        for entity_id, state in {
            "camera.back": _State("streaming", "Back"),
            "switch.back_detect": _State("on"),
            "switch.back_recordings": _State("on"),
        }.items():
            hass.states.values[entity_id] = state
            hass.entity_registry.platforms[entity_id] = "frigate"
        hass.states.values.pop("switch.front_recordings")
        hass.entity_registry.platforms.pop("switch.front_recordings")
        record = _paused_record(phase="resuming")
        storage = _Storage({"front": record})

        pending = await control.async_recover_transitions(hass, storage)
        finalized = await control.async_finalize_recovery_pending(
            hass, storage, pending["pending"]
        )
        back = await control.async_pause_camera(
            hass, storage, "back", operation_id="pause-back"
        )
        return storage, pending, finalized, back

    storage, pending, finalized, back = asyncio.run(scenario())

    assert pending["pending"] == ["front"]
    assert finalized == ["front"]
    assert storage.paused["front"]["phase"] == "error"
    assert storage.paused["front"]["resume_blocked"] is True
    assert storage.paused["front"]["switches"] == [
        "switch.front_detect",
        "switch.front_recordings",
    ]
    assert storage.paused["front"]["recovery_missing_targets"] == [
        "switch.front_recordings"
    ]
    assert back["phase"] == "paused"
