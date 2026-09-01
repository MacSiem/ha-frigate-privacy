"""Scheduler recovery remains active even when Frigate discovery is late."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "ha_frigate_privacy"


def _load_scheduler():
    const = sys.modules.setdefault(
        "homeassistant.const", types.ModuleType("homeassistant.const")
    )
    const.EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
    core = sys.modules.setdefault(
        "homeassistant.core", types.ModuleType("homeassistant.core")
    )
    core.Event = getattr(core, "Event", object)
    core.HomeAssistant = getattr(core, "HomeAssistant", object)
    core.callback = getattr(core, "callback", lambda function: function)
    helpers = sys.modules.setdefault(
        "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
    )
    helpers.__path__ = getattr(helpers, "__path__", [])
    event = sys.modules.setdefault(
        "homeassistant.helpers.event", types.ModuleType("homeassistant.helpers.event")
    )
    event.async_track_state_change_event = lambda *_args, **_kwargs: lambda: None
    event.async_track_point_in_utc_time = lambda *_args, **_kwargs: lambda: None
    event.async_track_time_change = lambda *_args, **_kwargs: lambda: None

    package = types.ModuleType("fpr_scheduler_recovery")
    package.__path__ = [str(PKG)]
    sys.modules["fpr_scheduler_recovery"] = package

    const_spec = importlib.util.spec_from_file_location(
        "fpr_scheduler_recovery.const", PKG / "const.py"
    )
    const_module = importlib.util.module_from_spec(const_spec)
    sys.modules["fpr_scheduler_recovery.const"] = const_module
    assert const_spec and const_spec.loader
    const_spec.loader.exec_module(const_module)

    control = types.ModuleType("fpr_scheduler_recovery.control")
    control.async_finalize_recovery_pending = None
    control.async_pause_cameras = None
    control.async_recover_transitions = None
    control.async_resume_camera = None
    control.discover_frigate_cameras = None
    control.ResumeAuthority = types.SimpleNamespace(
        DEADLINE="deadline", SCHEDULE="schedule"
    )
    sys.modules["fpr_scheduler_recovery.control"] = control

    failsafe = types.ModuleType("fpr_scheduler_recovery.failsafe")
    failsafe.decide_manual_override = lambda **_kwargs: {
        "override": False,
        "on_switches": [],
    }
    sys.modules["fpr_scheduler_recovery.failsafe"] = failsafe
    storage = types.ModuleType("fpr_scheduler_recovery.storage")
    storage.FrigatePrivacyStorage = object
    sys.modules["fpr_scheduler_recovery.storage"] = storage

    spec = importlib.util.spec_from_file_location(
        "fpr_scheduler_recovery.scheduler", PKG / "scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["fpr_scheduler_recovery.scheduler"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


scheduler_module = _load_scheduler()


class _Storage:
    def __init__(self, paused, schedules=None):
        self.paused = deepcopy(paused)
        self.schedules = deepcopy(schedules or [])

    async def async_get_schedules(self):
        return deepcopy(self.schedules)

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

    async def async_transition_paused(self, camera_id, phase, **updates):
        self.paused[camera_id].update(deepcopy(updates))
        self.paused[camera_id]["phase"] = phase
        return deepcopy(self.paused[camera_id])

    async def async_mark_overridden(self, camera_id, *, on_switches):
        self.paused[camera_id]["overridden"] = True
        self.paused[camera_id]["overridden_switches"] = list(on_switches)
        self.paused[camera_id]["override_active_schedule_ids"] = list(
            self.paused[camera_id].get("active_schedule_ids") or []
        )
        self.paused[camera_id]["phase"] = "active"
        self.paused[camera_id]["active"] = False
        self.paused[camera_id]["reason"] = "manual_override"
        return deepcopy(self.paused[camera_id])

    async def async_release_schedule_override(self, camera_id):
        self.paused[camera_id]["overridden"] = False
        self.paused[camera_id]["override_released"] = True
        self.paused[camera_id]["override_active_schedule_ids"] = []
        return deepcopy(self.paused[camera_id])


class _States:
    def get(self, _entity_id):
        return None


class _Hass:
    def __init__(self):
        self.states = _States()

    def async_create_task(self, coro):
        return asyncio.create_task(coro)


class _State:
    def __init__(self, state):
        self.state = state


class _MappedStates:
    def __init__(self, values):
        self.values = values

    def get(self, entity_id):
        return self.values.get(entity_id)


class _Bus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, data):
        self.events.append((event_type, deepcopy(data)))


class _Services:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, **_kwargs):
        self.calls.append((domain, service, deepcopy(data)))


class _OverrideHass(_Hass):
    def __init__(self, values):
        super().__init__()
        self.states = _MappedStates(values)
        self.bus = _Bus()
        self.services = _Services()


def test_camera_entity_override_is_detected_and_notification_is_redacted():
    async def scenario():
        now = datetime.now(timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "camera_entity_id": "camera.front",
                    "name": "Front Door",
                    "phase": "paused",
                    "active": True,
                    "source": "schedule",
                    "switches": [],
                    "camera_toggled": True,
                    "started_at": (now - timedelta(minutes=10)).isoformat(),
                }
            }
        )
        hass = _OverrideHass({"camera.front": _State("idle")})

        def decide(**kwargs):
            on_targets = []
            if (
                kwargs.get("camera_toggled")
                and kwargs.get("camera_entity_id")
                and kwargs.get("camera_state") == "idle"
            ):
                on_targets.append(kwargs["camera_entity_id"])
            return {
                "override": bool(on_targets),
                "in_grace": False,
                "on_switches": [],
                "on_targets": on_targets,
            }

        scheduler_module.decide_manual_override = decide
        scheduler = scheduler_module.FrigatePrivacyScheduler(hass, storage)
        await scheduler._async_handle_manual_overrides()
        return hass, storage

    hass, storage = asyncio.run(scenario())

    assert storage.paused["front"]["overridden"] is True
    event_data = hass.bus.events[0][1]
    assert event_data == {
        "reason": "managed_target_reenabled",
        "affected_target_count": 1,
    }
    notification = hass.services.calls[0][2]
    assert "Front Door" not in notification["message"]
    assert "camera.front" not in notification["message"]
    assert "front" not in notification["notification_id"]


def test_manual_override_never_delegates_authority_to_resume_targets():
    async def scenario():
        now = datetime.now(timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "camera_entity_id": "camera.front",
                    "phase": "paused",
                    "active": True,
                    "source": "manual",
                    "switches": ["switch.front_detect"],
                    "camera_toggled": True,
                    "started_at": (now - timedelta(minutes=10)).isoformat(),
                }
            }
        )
        hass = _OverrideHass(
            {
                "camera.front": _State("idle"),
                "switch.front_detect": _State("off"),
            }
        )

        scheduler_module.decide_manual_override = lambda **_kwargs: {
            "override": True,
            "in_grace": False,
            "on_switches": [],
            "on_targets": ["camera.front"],
        }

        async def forbidden_resume(*_args, **_kwargs):
            raise AssertionError("external state changes must never authorize resume")

        scheduler_module.async_resume_camera = forbidden_resume
        scheduler = scheduler_module.FrigatePrivacyScheduler(hass, storage)
        await scheduler._async_handle_manual_overrides()
        return hass, storage

    hass, storage = asyncio.run(scenario())

    assert storage.paused["front"]["overridden"] is True
    assert not any(
        domain in {"camera", "switch"}
        for domain, _service, _data in hass.services.calls
    )


def test_camera_entity_changed_by_pause_is_in_instant_override_watch():
    async def scenario():
        now = datetime.now(timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "camera_entity_id": "camera.front",
                    "phase": "paused",
                    "active": True,
                    "source": "manual",
                    "switches": [],
                    "camera_toggled": True,
                    "started_at": (now - timedelta(minutes=10)).isoformat(),
                }
            }
        )
        hass = _OverrideHass({"camera.front": _State("off")})
        watched = []

        def track(_hass, entity_ids, _callback):
            watched.extend(entity_ids)
            return lambda: None

        scheduler_module.async_track_state_change_event = track
        scheduler = scheduler_module.FrigatePrivacyScheduler(hass, storage)
        await scheduler._async_refresh_override_watch()
        return watched

    assert asyncio.run(scenario()) == ["camera.front"]


def test_expired_pause_is_reconciled_without_discovered_cameras():
    async def scenario():
        now = datetime.now(timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "phase": "paused",
                    "active": True,
                    "source": "manual",
                    "switches": ["switch.front_detect"],
                    "started_at": (now - timedelta(hours=1)).isoformat(),
                    "ends_at": (now - timedelta(minutes=1)).isoformat(),
                }
            }
        )
        calls = []

        async def recover(_hass, _storage):
            return {"recovered": [], "held": []}

        async def resume(_hass, _storage, camera_id, *, authority, reason):
            calls.append((camera_id, authority, reason))
            return {"camera_id": camera_id, "resumed": False, "phase": "error"}

        scheduler_module.async_recover_transitions = recover
        scheduler_module.async_resume_camera = resume
        scheduler_module.discover_frigate_cameras = lambda _hass: []
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), storage)
        scheduler._async_handle_manual_overrides = lambda: asyncio.sleep(0)
        scheduler._async_refresh_override_watch = lambda: asyncio.sleep(0)
        await scheduler.async_tick(now)
        return calls

    assert asyncio.run(scenario()) == [
        ("front", "deadline", "manual_deadline_elapsed")
    ]


def test_overlapping_ticks_are_serialized():
    async def scenario():
        active = 0
        maximum = 0

        async def recover(_hass, _storage):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {"recovered": [], "held": []}

        scheduler_module.async_recover_transitions = recover
        scheduler_module.discover_frigate_cameras = lambda _hass: []
        storage = _Storage({})
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), storage)
        scheduler._async_handle_manual_overrides = lambda: asyncio.sleep(0)
        scheduler._async_refresh_override_watch = lambda: asyncio.sleep(0)
        await asyncio.gather(scheduler.async_tick(), scheduler.async_tick())
        return maximum

    assert asyncio.run(scenario()) == 1


def test_overlapping_schedule_keeps_privacy_until_last_window_exits():
    async def scenario():
        now = datetime(2026, 8, 31, 20, 30, tzinfo=timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "phase": "paused",
                    "active": True,
                    "source": "schedule",
                    "schedule_id": "A",
                    "active_schedule_ids": ["A"],
                    "switches": ["switch.front_detect"],
                }
            },
            schedules=[
                {
                    "id": "B",
                    "enabled": True,
                    "days": [1],
                    "startHour": 20,
                    "startMin": 0,
                    "endHour": 21,
                    "endMin": 0,
                }
            ],
        )
        calls = []

        async def recover(_hass, _storage):
            return {"recovered": [], "held": []}

        async def pause(_hass, _storage, refs, **kwargs):
            calls.append(("pause", tuple(refs), kwargs.get("schedule_id")))
            return {"ok": True, "phase": "paused", "results": []}

        async def resume(_hass, _storage, camera_id, *, authority, reason):
            calls.append(("resume", camera_id, authority, reason))
            return {"camera_id": camera_id, "resumed": True, "phase": "active"}

        scheduler_module.async_recover_transitions = recover
        scheduler_module.async_pause_cameras = pause
        scheduler_module.async_resume_camera = resume
        scheduler_module.discover_frigate_cameras = lambda _hass: [
            {"camera_id": "front"}
        ]
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), storage)
        scheduler._async_handle_manual_overrides = lambda: asyncio.sleep(0)
        scheduler._async_refresh_override_watch = lambda: asyncio.sleep(0)
        await scheduler.async_tick(now)
        return storage, calls

    storage, calls = asyncio.run(scenario())

    assert not any(call[0] == "resume" for call in calls)
    assert storage.paused["front"]["active_schedule_ids"] == ["B"]
    assert storage.paused["front"]["schedule_id"] == "B"


def test_schedule_override_suppresses_reapply_for_unchanged_active_coverage():
    async def scenario():
        now = datetime(2026, 8, 31, 20, 30, tzinfo=timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "phase": "active",
                    "active": False,
                    "source": "schedule",
                    "schedule_id": "A",
                    "active_schedule_ids": ["A"],
                    "override_active_schedule_ids": ["A"],
                    "overridden": True,
                    "reason": "manual_override",
                }
            },
            schedules=[
                {
                    "id": "A",
                    "enabled": True,
                    "days": [1],
                    "startHour": 20,
                    "startMin": 0,
                    "endHour": 21,
                    "endMin": 0,
                }
            ],
        )
        calls = []

        async def recover(_hass, _storage):
            return {"recovered": [], "held": [], "pending": []}

        async def pause(_hass, _storage, refs, **_kwargs):
            calls.append(("pause", tuple(refs)))
            return {"ok": True, "phase": "paused", "results": []}

        scheduler_module.async_recover_transitions = recover
        scheduler_module.async_pause_cameras = pause
        scheduler_module.discover_frigate_cameras = lambda _hass: [
            {"camera_id": "front"}
        ]
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), storage)
        scheduler._async_handle_manual_overrides = lambda: asyncio.sleep(0)
        scheduler._async_refresh_override_watch = lambda: asyncio.sleep(0)
        await scheduler.async_tick(now)
        return storage, calls

    storage, calls = asyncio.run(scenario())

    assert calls == []
    assert storage.paused["front"]["overridden"] is True


def test_schedule_override_is_released_after_coverage_ends():
    async def scenario():
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "phase": "active",
                    "active": False,
                    "source": "schedule",
                    "schedule_id": "A",
                    "active_schedule_ids": ["A"],
                    "override_active_schedule_ids": ["A"],
                    "overridden": True,
                    "reason": "manual_override",
                }
            }
        )

        async def recover(_hass, _storage):
            return {"recovered": [], "held": [], "pending": []}

        scheduler_module.async_recover_transitions = recover
        scheduler_module.discover_frigate_cameras = lambda _hass: []
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), storage)
        scheduler._async_handle_manual_overrides = lambda: asyncio.sleep(0)
        scheduler._async_refresh_override_watch = lambda: asyncio.sleep(0)
        await scheduler.async_tick(datetime.now(timezone.utc))
        return storage

    storage = asyncio.run(scenario())

    assert storage.paused["front"]["overridden"] is False
    assert storage.paused["front"]["override_released"] is True


def test_manual_deadline_inside_schedule_does_not_resume_camera():
    async def scenario():
        now = datetime(2026, 8, 31, 20, 30, tzinfo=timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "phase": "paused",
                    "active": True,
                    "source": "manual",
                    "switches": ["switch.front_recordings"],
                    "ends_at": (now - timedelta(minutes=1)).isoformat(),
                }
            },
            schedules=[
                {
                    "id": "B",
                    "enabled": True,
                    "days": [1],
                    "startHour": 20,
                    "startMin": 0,
                    "endHour": 21,
                    "endMin": 0,
                }
            ],
        )
        calls = []

        async def recover(_hass, _storage):
            return {"recovered": [], "held": []}

        async def pause(_hass, _storage, refs, **kwargs):
            calls.append(("pause", tuple(refs), kwargs.get("schedule_id")))
            state = storage.paused[refs[0]]
            state["active_schedule_ids"] = [kwargs["schedule_id"]]
            return {"ok": True, "phase": "paused", "results": []}

        async def resume(_hass, _storage, camera_id, *, authority, reason):
            calls.append(("resume", camera_id, authority, reason))
            return {"camera_id": camera_id, "resumed": True, "phase": "active"}

        scheduler_module.async_recover_transitions = recover
        scheduler_module.async_pause_cameras = pause
        scheduler_module.async_resume_camera = resume
        scheduler_module.discover_frigate_cameras = lambda _hass: [
            {"camera_id": "front"}
        ]
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), storage)
        scheduler._async_handle_manual_overrides = lambda: asyncio.sleep(0)
        scheduler._async_refresh_override_watch = lambda: asyncio.sleep(0)
        await scheduler.async_tick(now)
        return storage, calls

    storage, calls = asyncio.run(scenario())

    assert ("pause", ("front",), "B") in calls
    assert not any(call[0] == "resume" for call in calls)
    assert storage.paused["front"]["active_schedule_ids"] == ["B"]


def test_exact_deadline_callback_is_unique_and_cancelled_on_stop():
    async def scenario():
        now = datetime.now(timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "phase": "paused",
                    "active": True,
                    "source": "manual",
                    "operation_id": "pause-front-1",
                    "switches": ["switch.front_detect"],
                    "ends_at": (now + timedelta(minutes=5)).isoformat(),
                }
            }
        )
        scheduled = []
        cancelled = []

        def track(_hass, _callback, when):
            scheduled.append(when)

            def unsub():
                cancelled.append(when)

            return unsub

        scheduler_module.async_track_point_in_utc_time = track
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), storage)
        await scheduler._async_refresh_deadlines()
        await scheduler._async_refresh_deadlines()
        await scheduler.async_stop()
        return scheduler, scheduled, cancelled

    scheduler, scheduled, cancelled = asyncio.run(scenario())

    assert len(scheduled) == 1
    assert cancelled == scheduled
    assert scheduler._deadline_unsubs == {}


def test_deadline_callback_recomputes_local_wall_clock():
    async def scenario():
        now = datetime.now(timezone.utc)
        storage = _Storage(
            {
                "front": {
                    "camera_id": "front",
                    "phase": "paused",
                    "active": True,
                    "source": "manual",
                    "operation_id": "pause-front-1",
                    "switches": ["switch.front_detect"],
                    "ends_at": (now + timedelta(minutes=5)).isoformat(),
                }
            }
        )
        callbacks = []

        def track(_hass, callback, _when):
            callbacks.append(callback)
            return lambda: None

        scheduler_module.async_track_point_in_utc_time = track
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), storage)
        received = []

        async def tick(tick_now=None):
            received.append(tick_now)

        scheduler.async_tick = tick
        await scheduler._async_refresh_deadlines()
        callbacks[0](datetime(2026, 8, 31, 18, 30, tzinfo=timezone.utc))
        await asyncio.sleep(0)
        await scheduler.async_stop()
        return received

    assert asyncio.run(scenario()) == [None]


def test_stop_cancels_owned_inflight_tasks_before_side_effect():
    async def scenario():
        scheduler = scheduler_module.FrigatePrivacyScheduler(_Hass(), _Storage({}))
        side_effects = []

        async def queued_work():
            await asyncio.sleep(0.05)
            side_effects.append("ran")

        scheduler._create_task(queued_work())
        await scheduler.async_stop()
        await asyncio.sleep(0.06)
        return scheduler, side_effects

    scheduler, side_effects = asyncio.run(scenario())

    assert side_effects == []
    assert scheduler._owned_tasks == set()


def test_schedule_windows_use_local_wall_time_across_dst_boundaries():
    warsaw = ZoneInfo("Europe/Warsaw")
    spring = datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc).astimezone(
        warsaw
    )
    spring_schedule = {
        "days": [7],
        "startHour": 3,
        "startMin": 0,
        "endHour": 4,
        "endMin": 0,
    }
    assert spring.hour == 3
    assert scheduler_module.schedule_in_window(spring_schedule, spring)

    repeated_hour_schedule = {
        "days": [7],
        "startHour": 2,
        "startMin": 0,
        "endHour": 3,
        "endMin": 0,
    }
    first_230 = datetime(
        2026, 10, 25, 0, 30, tzinfo=timezone.utc
    ).astimezone(warsaw)
    second_230 = datetime(
        2026, 10, 25, 1, 30, tzinfo=timezone.utc
    ).astimezone(warsaw)
    assert first_230.hour == second_230.hour == 2
    assert scheduler_module.schedule_in_window(
        repeated_hour_schedule, first_230
    )
    assert scheduler_module.schedule_in_window(
        repeated_hour_schedule, second_230
    )
