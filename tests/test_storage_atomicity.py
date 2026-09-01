"""Persistence failures must not corrupt the process-local durable snapshot."""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import sys
import types
from copy import deepcopy
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "ha_frigate_privacy"


def _load_storage():
    core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )
    core.HomeAssistant = getattr(core, "HomeAssistant", object)
    helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    helpers.__path__ = getattr(helpers, "__path__", [])
    helper_storage = sys.modules.setdefault(
        "homeassistant.helpers.storage",
        types.ModuleType("homeassistant.helpers.storage"),
    )

    class _BootstrapStore:
        def __init__(self, *_args, **kwargs):
            self.saved = None
            self._error_to_swallow = None
            self.init_kwargs = kwargs

        async def async_load(self):
            return deepcopy(self.saved)

        async def async_save(self, data):
            """Model HA Store's historically surprising swallowed write error."""
            try:
                await self._async_write_data(data)
            except Exception:  # The real Store swallows WriteError/serialization errors.
                return

        async def _async_write_data(self, data):
            if self._error_to_swallow is not None:
                raise self._error_to_swallow
            self.saved = deepcopy(data)

    # Test collection is shared across lightweight HA stubs. Always install
    # this exact Store contract so ordering cannot weaken the swallowed-write
    # regression model.
    helper_storage.Store = _BootstrapStore
    package = types.ModuleType("fpr_storage_atomicity")
    package.__path__ = [str(PKG)]
    sys.modules["fpr_storage_atomicity"] = package
    for name in ("const", "storage"):
        spec = importlib.util.spec_from_file_location(
            f"fpr_storage_atomicity.{name}", PKG / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"fpr_storage_atomicity.{name}"] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
    return sys.modules["fpr_storage_atomicity.storage"]


storage_module = _load_storage()


def test_privacy_store_uses_atomic_private_home_assistant_storage():
    storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())

    assert storage._store.init_kwargs["private"] is True
    assert storage._store.init_kwargs["atomic_writes"] is True


class _FailingStore:
    def __init__(self, data):
        self.data = deepcopy(data)

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, _data):
        raise RuntimeError("fixture durable save failure")


class _WorkingStore:
    def __init__(self, data):
        self.data = deepcopy(data)
        self.save_count = 0

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        self.data = deepcopy(data)
        self.save_count += 1


class _CancelledStore:
    def __init__(self, data):
        self.data = deepcopy(data)

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, _data):
        raise asyncio.CancelledError


def test_failed_transition_restores_previous_in_memory_snapshot():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _FailingStore(
            {
                "schedules": [],
                "paused": {
                    "front": {
                        "camera_id": "front",
                        "phase": "paused",
                        "active": True,
                        "switches": ["switch.front_detect"],
                    }
                },
            }
        )
        before = await storage.async_get_state()
        try:
            await storage.async_transition_paused("front", "resuming")
        except RuntimeError as error:
            assert "durable save" in str(error)
        else:
            raise AssertionError("save failure must be surfaced")
        after = await storage.async_get_state()
        return before, after

    before, after = asyncio.run(scenario())
    assert after == before
    assert after["paused"]["front"]["phase"] == "paused"


def test_failed_schedule_save_does_not_create_ghost_schedule():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _FailingStore({"schedules": [], "paused": {}})
        await storage.async_get_state()
        try:
            await storage.async_upsert_schedule(
                {
                    "id": "evening",
                    "days": [1],
                    "startHour": 18,
                    "startMin": 0,
                    "endHour": 20,
                    "endMin": 0,
                }
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("save failure must be surfaced")
        return await storage.async_get_schedules()

    assert asyncio.run(scenario()) == []


def test_store_write_error_swallowed_by_home_assistant_is_surfaced_and_rolled_back():
    """A real HA Store logs selected write failures instead of raising them."""

    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        store = storage._store
        store.saved = {"schedules": [], "paused": {}}
        await storage.async_get_state()
        store._error_to_swallow = RuntimeError("simulated WriteError")
        try:
            await storage.async_upsert_schedule({"id": "evening", "days": [1]})
        except storage_module.StorageWriteError as error:
            assert "durably" in str(error)
        else:
            raise AssertionError("a swallowed HA Store error must be surfaced")
        return await storage.async_get_schedules(), deepcopy(store.saved)

    schedules, durable = asyncio.run(scenario())

    assert schedules == []
    assert durable == {"schedules": [], "paused": {}}


def test_schedule_text_is_normalized_to_bounded_storage_fields():
    normalized = storage_module.FrigatePrivacyStorage._normalize_schedule(
        {
            "id": "i" * 500,
            "label": "l" * 500,
            "days": [1],
        }
    )

    assert len(normalized["id"]) == 128
    assert len(normalized["label"]) == 120


def test_schedule_operation_retry_replays_one_atomic_result():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        store = _WorkingStore({"schedules": [], "paused": {}})
        storage._store = store
        payload = {
            "id": "evening",
            "label": "Evening",
            "days": [1],
            "startHour": 18,
            "startMin": 0,
            "endHour": 20,
            "endMin": 0,
        }
        first = await storage.async_apply_schedule_operation(
            operation_id="schedule-op-1",
            action="upsert",
            schedule=payload,
        )
        replay = await storage.async_apply_schedule_operation(
            operation_id="schedule-op-1",
            action="upsert",
            schedule=payload,
        )
        return store, first, replay, await storage.async_get_schedules()

    store, first, replay, schedules = asyncio.run(scenario())

    assert replay == first
    assert store.save_count == 1
    assert [item["id"] for item in schedules] == ["evening"]


def test_schedule_operation_id_rejects_a_different_normalized_payload():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore({"schedules": [], "paused": {}})
        await storage.async_apply_schedule_operation(
            operation_id="schedule-op-1",
            action="upsert",
            schedule={"id": "evening", "label": "Evening", "days": [1]},
        )
        try:
            await storage.async_apply_schedule_operation(
                operation_id="schedule-op-1",
                action="upsert",
                schedule={"id": "evening", "label": "Changed", "days": [1]},
            )
        except ValueError as error:
            return str(error), await storage.async_get_schedules()
        raise AssertionError("payload mismatch must fail closed")

    error, schedules = asyncio.run(scenario())

    assert "payload mismatch" in error
    assert schedules[0]["label"] == "Evening"


def test_cancelled_save_restores_previous_in_memory_snapshot():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _CancelledStore(
            {
                "schedules": [],
                "paused": {
                    "front": {
                        "camera_id": "front",
                        "phase": "paused",
                        "active": True,
                    }
                },
            }
        )
        before = await storage.async_get_state()
        try:
            await storage.async_transition_paused("front", "resuming")
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("cancellation must be preserved")
        return before, await storage.async_get_state()

    before, after = asyncio.run(scenario())
    assert after == before


def test_evicted_schedule_operation_id_fails_closed():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore({"schedules": [], "paused": {}})
        old = [{"id": "old", "label": "OLD", "days": [1]}]
        await storage.async_apply_schedule_operation(
            operation_id="old-op", action="replace_all", schedules=old
        )
        for index in range(65):
            await storage.async_apply_schedule_operation(
                operation_id=f"new-op-{index}",
                action="replace_all",
                schedules=[
                    {"id": "current", "label": f"NEW-{index}", "days": [1]}
                ],
            )
        try:
            await storage.async_apply_schedule_operation(
                operation_id="old-op", action="replace_all", schedules=old
            )
        except ValueError as error:
            return str(error), await storage.async_get_schedules()
        raise AssertionError("an evicted operation id must fail closed")

    error, schedules = asyncio.run(scenario())
    assert "expired" in error
    assert schedules[0]["label"] == "NEW-64"


def test_schedule_upsert_requires_stable_explicit_id():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore({"schedules": [], "paused": {}})
        try:
            await storage.async_apply_schedule_operation(
                operation_id="upsert-without-id",
                action="upsert",
                schedule={"label": "Evening", "days": [1]},
            )
        except ValueError as error:
            return str(error), await storage.async_get_schedules()
        raise AssertionError("upsert without an explicit id must fail closed")

    error, schedules = asyncio.run(scenario())
    assert "id is required" in error
    assert schedules == []


def test_malformed_replay_state_is_preserved_as_integrity_evidence_and_blocks_mutation():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore(
            {
                "schedules": {"not": "a list"},
                "schedule_operations": "not-a-list",
                "schedule_operation_filter": "not-base64",
                "camera_operation_filters": {
                    "front": "definitely-not-a-valid-filter",
                },
                "paused": ["not-a-map"],
            }
        )
        before = await storage.async_load()
        try:
            await storage.async_apply_schedule_operation(
                operation_id="new-op",
                action="replace_all",
                schedules=[],
            )
        except storage_module.ReplayIntegrityError as error:
            error_text = str(error)
        else:
            raise AssertionError("corrupt replay state must block mutation")
        after = await storage.async_load()
        return before, after, error_text

    before, after, error_text = asyncio.run(scenario())
    assert before == after
    assert before["paused"] == {}
    assert before["replay_integrity"]["state"] == "corrupt"
    assert len(before["replay_integrity"]["errors"]) == 2
    assert all("digest" in item for item in before["replay_integrity"]["errors"])
    assert "integrity" in error_text


def test_missing_replay_fields_are_a_clean_install_not_corruption():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore({"schedules": [], "paused": {}})
        result = await storage.async_apply_schedule_operation(
            operation_id="new-op",
            action="replace_all",
            schedules=[],
        )
        return await storage.async_load(), result

    state, result = asyncio.run(scenario())
    assert result == {"schedules": []}
    assert state["replay_integrity"]["state"] == "valid"
    assert state["schedule_operation_filter"]["version"] == 2


def test_present_replay_corruption_variants_never_normalize_as_empty_filter():
    replay = sys.modules["fpr_storage_atomicity.replay"]
    corrupt_values = (
        [],
        "not-base64",
        base64.b64encode(b"too-short").decode("ascii"),
        {"version": 2, "bits": "not-base64", "accepted": 0},
        {"version": 2, "bits": replay.new_replay_filter()["bits"], "accepted": -1},
    )

    for corrupt in corrupt_values:
        try:
            replay.normalize_replay_filter(corrupt)
        except replay.ReplayFilterError:
            continue
        raise AssertionError(f"corrupt replay state was accepted: {type(corrupt)!r}")


def test_legacy_valid_filter_migrates_without_losing_replay_protection():
    replay = sys.modules["fpr_storage_atomicity.replay"]
    legacy_bits = bytearray(replay.REPLAY_FILTER_BYTES)
    for position in replay._positions("replace_all", "old-op"):
        legacy_bits[position // 8] |= 1 << (position % 8)
    legacy = base64.b64encode(legacy_bits).decode("ascii")

    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore(
            {
                "schedules": [],
                "paused": {},
                "schedule_operation_filter": legacy,
            }
        )
        try:
            await storage.async_apply_schedule_operation(
                operation_id="old-op", action="replace_all", schedules=[]
            )
        except ValueError as error:
            old_error = str(error)
        else:
            raise AssertionError("legacy replay id must remain blocked")
        await storage.async_apply_schedule_operation(
            operation_id="new-op", action="replace_all", schedules=[]
        )
        return old_error, await storage.async_load()

    old_error, state = asyncio.run(scenario())
    assert "expired" in old_error
    assert state["schedule_operation_filter"]["version"] == 2


def test_replay_filter_saturation_fails_closed_before_schedule_mutation():
    replay = sys.modules["fpr_storage_atomicity.replay"]
    saturated = replay.new_replay_filter()
    saturated["accepted"] = replay.REPLAY_FILTER_MAX_ACCEPTED

    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore(
            {
                "schedules": [{"id": "keep", "days": [1]}],
                "paused": {},
                "schedule_operation_filter": saturated,
            }
        )
        before = await storage.async_get_schedules()
        try:
            await storage.async_apply_schedule_operation(
                operation_id="new-op", action="replace_all", schedules=[]
            )
        except replay.ReplayFilterSaturatedError as error:
            error_text = str(error)
        else:
            raise AssertionError("saturated replay filter must fail closed")
        return before, await storage.async_get_schedules(), error_text

    before, after, error_text = asyncio.run(scenario())
    assert after == before
    assert "saturated" in error_text


def test_camera_replay_filter_saturation_blocks_reservation_before_side_effects():
    replay = sys.modules["fpr_storage_atomicity.replay"]
    saturated = replay.new_replay_filter()
    saturated["accepted"] = replay.REPLAY_FILTER_MAX_ACCEPTED

    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore(
            {
                "schedules": [],
                "paused": {},
                "camera_operation_filters": {"front": saturated},
            }
        )
        before = await storage.async_load()
        try:
            await storage.async_reserve_camera_operation(
                "front", "pause", "new-op"
            )
        except replay.ReplayFilterSaturatedError as error:
            error_text = str(error)
        else:
            raise AssertionError("saturated camera replay filter must fail closed")
        return before, await storage.async_load(), error_text

    before, after, error_text = asyncio.run(scenario())
    assert after == before
    assert "saturated" in error_text


def test_manual_override_is_a_truthful_terminal_active_record():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore(
            {
                "schedules": [],
                "paused": {
                    "front": {
                        "camera_id": "front",
                        "phase": "paused",
                        "active": True,
                        "source": "schedule",
                        "switches": ["switch.front_detect"],
                    }
                },
            }
        )
        record = await storage.async_mark_overridden(
            "front", on_switches=["switch.front_detect"]
        )
        return record, await storage.async_get_state(), await storage.async_get_paused()

    record, state, active = asyncio.run(scenario())
    assert record["phase"] == "active"
    assert record["active"] is False
    assert record["desired_state"] == "active"
    assert record["reason"] == "manual_override"
    assert record["overridden_switches"] == ["switch.front_detect"]
    assert active == {}
    assert state["last_operations"]["front"]["reason"] == "manual_override"


def test_legacy_overridden_active_record_is_migrated_to_truthful_terminal_state():
    async def scenario():
        storage = storage_module.FrigatePrivacyStorage(types.SimpleNamespace())
        storage._store = _WorkingStore(
            {
                "schedules": [],
                "paused": {
                    "front": {
                        "camera_id": "front",
                        "phase": "paused",
                        "active": True,
                        "overridden": True,
                        "overridden_switches": ["switch.front_detect"],
                        "target_outcomes": {"switch.front_detect": "on"},
                    }
                },
            }
        )
        return await storage.async_load()

    state = asyncio.run(scenario())
    record = state["paused"]["front"]
    assert record["phase"] == "active"
    assert record["active"] is False
    assert record["reason"] == "manual_override"
    assert record["target_outcomes"] == {"switch.front_detect": "on"}
