"""Server-side schedule application for Frigate Privacy."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_change,
)

from .const import DATA_RECOVERY_READY, DOMAIN
from .control import (
    ResumeAuthority,
    async_finalize_recovery_pending,
    async_pause_cameras,
    async_recover_transitions,
    async_resume_camera,
    discover_frigate_cameras,
)
from .failsafe import decide_manual_override
from .storage import FrigatePrivacyStorage

_LOGGER = logging.getLogger(__name__)
RECOVERY_ENTITY_GRACE = timedelta(seconds=30)


def _private_notification_id(kind: str, camera_id: str) -> str:
    """Return a stable notification id without exposing household topology."""
    reference = hashlib.sha256(f"{kind}\0{camera_id}".encode()).hexdigest()[:16]
    return f"{DOMAIN}_{kind}_{reference}"


class FrigatePrivacyScheduler:
    """Apply privacy schedules once per minute and after HA starts."""

    def __init__(
        self, hass: HomeAssistant, storage: FrigatePrivacyStorage
    ) -> None:
        """Initialize scheduler."""
        self.hass = hass
        self.storage = storage
        self._unsub_time = None
        self._unsub_start = None
        self._unsub_states = None
        self._watched_targets: frozenset[str] = frozenset()
        self._tick_lock = asyncio.Lock()
        self._owned_tasks: set[asyncio.Task] = set()
        self._deadline_unsubs: dict[str, tuple[str, Any]] = {}
        self._recovery_grace_until: datetime | None = None
        self._recovery_grace_unsub = None
        self._stopping = False

    def async_start(self) -> None:
        """Start minute ticks and re-check on HA start."""
        self._stopping = False
        if self._unsub_time is None:
            self._unsub_time = async_track_time_change(
                self.hass, self._handle_time, second=0
            )
        if self.hass.is_running:
            self._create_task(self.async_tick())
        else:
            self._unsub_start = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._handle_started
            )

    async def async_stop(self) -> None:
        """Stop callbacks and cancel every queued/in-flight owned task."""
        self._stopping = True
        if self._unsub_time:
            self._unsub_time()
            self._unsub_time = None
        if self._unsub_start:
            self._unsub_start()
            self._unsub_start = None
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        self._watched_targets = frozenset()
        for _, unsubscribe in self._deadline_unsubs.values():
            unsubscribe()
        self._deadline_unsubs.clear()
        self._cancel_recovery_grace()
        tasks = list(self._owned_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._owned_tasks.clear()

    def _create_task(self, coro: Any) -> asyncio.Task | None:
        """Create and retain an owned task so unload can cancel it safely."""
        if self._stopping:
            close = getattr(coro, "close", None)
            if close:
                close()
            return None
        task = self.hass.async_create_task(coro)
        self._owned_tasks.add(task)
        task.add_done_callback(self._owned_tasks.discard)
        return task

    def async_request_tick(self) -> None:
        """Queue one owned reconciliation tick."""
        self._create_task(self.async_tick())

    @callback
    def _handle_started(self, _: Event) -> None:
        """Re-arm schedule state after Home Assistant startup."""
        self._create_task(self.async_tick())

    @callback
    def _handle_time(self, now: datetime) -> None:
        """Schedule a tick from async_track_time_change."""
        self._create_task(self.async_tick(now))

    async def async_tick(self, now: datetime | None = None) -> None:
        """Apply active windows and exit inactive windows."""
        async with self._tick_lock:
            await self._async_tick_locked(now)

    async def _async_tick_locked(self, now: datetime | None = None) -> None:
        """Run one serialized reconciliation and scheduling tick."""
        now = now or datetime.now().astimezone()
        recovery = await async_recover_transitions(self.hass, self.storage)
        pending = list(recovery.get("pending") or [])
        if pending:
            utc_now = datetime.now(timezone.utc)
            if self._recovery_grace_until is None:
                self._recovery_grace_until = utc_now + RECOVERY_ENTITY_GRACE

                @callback
                def _grace_reached(_utc_now: datetime) -> None:
                    self._recovery_grace_unsub = None
                    self._create_task(self.async_tick())

                self._recovery_grace_unsub = async_track_point_in_utc_time(
                    self.hass,
                    _grace_reached,
                    self._recovery_grace_until,
                )
            if utc_now < self._recovery_grace_until:
                if hasattr(self.hass, "data"):
                    self.hass.data.setdefault(DOMAIN, {})[
                        DATA_RECOVERY_READY
                    ] = False
                await self._async_refresh_override_watch()
                await self._async_refresh_deadlines()
                return
            await async_finalize_recovery_pending(
                self.hass, self.storage, pending
            )
            recovery = await async_recover_transitions(self.hass, self.storage)
            pending = list(recovery.get("pending") or [])
        if not pending:
            self._cancel_recovery_grace()
        if hasattr(self.hass, "data"):
            self.hass.data.setdefault(DOMAIN, {})[DATA_RECOVERY_READY] = not pending
        if pending:
            await self._async_refresh_override_watch()
            await self._async_refresh_deadlines()
            return
        schedules = await self.storage.async_get_schedules()
        cameras = discover_frigate_cameras(self.hass)
        camera_ids = [item["camera_id"] for item in cameras]

        active = {
            schedule["id"]: schedule
            for schedule in schedules
            if schedule.get("enabled") and schedule_in_window(schedule, now)
        }

        paused_all = await self.storage.async_get_paused(None) or {}
        schedule_covered = {
            camera_id: state
            for camera_id, state in paused_all.items()
            if state.get("source") == "schedule"
            or state.get("active_schedule_ids")
        }

        active_ids = sorted(active)
        active_id_set = set(active_ids)
        try:
            all_records = await self.storage.async_get_paused(
                None, include_inactive=True
            ) or {}
        except TypeError:  # Compatibility with small unit-test doubles.
            all_records = paused_all
        terminal_schedule_overrides = {
            camera_id: state
            for camera_id, state in all_records.items()
            if state.get("source") == "schedule"
            and state.get("overridden")
            and not state.get("active", True)
        }
        if not active_id_set:
            release = getattr(
                self.storage, "async_release_schedule_override", None
            )
            if release is not None:
                for camera_id in terminal_schedule_overrides:
                    await release(camera_id)
        suppressed_for_current_coverage = {
            camera_id
            for camera_id, state in terminal_schedule_overrides.items()
            if set(
                state.get("override_active_schedule_ids")
                or state.get("active_schedule_ids")
                or ([state.get("schedule_id")] if state.get("schedule_id") else [])
            )
            == active_id_set
        }
        if active_ids:
            # Schedule windows are union coverage. A camera remains private while
            # at least one window is active, even when the window that originally
            # created the pause has ended.
            for camera_id, state in schedule_covered.items():
                if (
                    state.get("source") == "schedule"
                    and state.get("active_schedule_ids") != active_ids
                ):
                    await self.storage.async_transition_paused(
                        camera_id,
                        state.get("phase") or "paused",
                        schedule_id=active_ids[0],
                        active_schedule_ids=active_ids,
                    )

            refs = [
                camera_id
                for camera_id in camera_ids
                if camera_id not in suppressed_for_current_coverage
                if (state := paused_all.get(camera_id)) is None
                or (
                    state.get("source") != "schedule"
                    and set(state.get("active_schedule_ids") or [])
                    != active_id_set
                )
            ]
            if refs:
                _LOGGER.debug(
                    "Applying Frigate Privacy schedule coverage (%s windows, %s cameras)",
                    len(active_ids),
                    len(refs),
                )
                await async_pause_cameras(
                    self.hass,
                    self.storage,
                    refs,
                    stream_type="all",
                    source="schedule",
                    schedule_id=active_ids[0],
                )
                for camera_id in refs:
                    state = await self.storage.async_get_paused(camera_id)
                    if state and state.get("source") == "schedule":
                        await self.storage.async_transition_paused(
                            camera_id,
                            state.get("phase") or "paused",
                            schedule_id=active_ids[0],
                            active_schedule_ids=active_ids,
                        )

        for camera_id, state in schedule_covered.items():
            if state.get("resume_blocked"):
                continue
            if active_id_set:
                continue
            if state.get("source") == "schedule":
                await async_resume_camera(
                    self.hass,
                    self.storage,
                    camera_id,
                    authority=ResumeAuthority.SCHEDULE,
                    reason="schedule_window_ended",
                )
            else:
                await self.storage.async_transition_paused(
                    camera_id,
                    state.get("phase") or "paused",
                    schedule_id=None,
                    active_schedule_ids=[],
                )

        paused_all = await self.storage.async_get_paused(None) or {}
        for camera_id, state in paused_all.items():
            if state.get("source") == "schedule" or state.get("resume_blocked"):
                continue
            if active_id_set:
                continue
            ends_at = _parse_datetime(state.get("ends_at"))
            if ends_at and datetime.now(timezone.utc) >= ends_at:
                await async_resume_camera(
                    self.hass,
                    self.storage,
                    camera_id,
                    authority=ResumeAuthority.DEADLINE,
                    reason="manual_deadline_elapsed",
                )

        await self._async_handle_manual_overrides()
        await self._async_refresh_override_watch()
        await self._async_refresh_deadlines()

    async def _async_refresh_deadlines(self) -> None:
        """Keep exactly one callback for each future manual pause deadline."""
        paused_all = await self.storage.async_get_paused(None) or {}
        now = datetime.now(timezone.utc)
        desired: dict[str, tuple[str, datetime]] = {}
        for camera_id, state in paused_all.items():
            if state.get("source") == "schedule" or state.get("resume_blocked"):
                continue
            deadline = _parse_datetime(state.get("ends_at"))
            if deadline and deadline > now:
                key = f"{state.get('operation_id') or camera_id}:{deadline.isoformat()}"
                desired[camera_id] = (key, deadline)

        for camera_id, (key, unsubscribe) in list(self._deadline_unsubs.items()):
            wanted = desired.get(camera_id)
            if wanted and wanted[0] == key:
                continue
            unsubscribe()
            self._deadline_unsubs.pop(camera_id, None)

        for camera_id, (key, deadline) in desired.items():
            if camera_id in self._deadline_unsubs:
                continue

            @callback
            def _deadline_reached(
                _utc_now: datetime,
                *,
                target_camera_id: str = camera_id,
            ) -> None:
                self._deadline_unsubs.pop(target_camera_id, None)
                # The HA point-in-time callback supplies UTC. Recompute the
                # local wall clock inside async_tick so schedule windows are
                # never evaluated against UTC by accident.
                self._create_task(self.async_tick())

            unsubscribe = async_track_point_in_utc_time(
                self.hass, _deadline_reached, deadline
            )
            self._deadline_unsubs[camera_id] = (key, unsubscribe)

    def _cancel_recovery_grace(self) -> None:
        """Cancel and clear the bounded late-entity recovery grace callback."""
        if self._recovery_grace_unsub:
            self._recovery_grace_unsub()
            self._recovery_grace_unsub = None
        self._recovery_grace_until = None

    async def _async_handle_manual_overrides(self) -> None:
        """Detect pauses whose switches were re-enabled outside the integration.

        A state change outside this integration is evidence that privacy is no
        longer enforced, not authority to re-enable any other target. Both
        manual and scheduled pauses therefore become a truthful terminal
        ``manual_override`` record without additional control side effects.
        """
        paused_all = await self.storage.async_get_paused(None) or {}
        for camera_id, state in paused_all.items():
            if state.get("resume_blocked") or state.get("overridden"):
                continue
            switches = list(state.get("switches") or [])
            camera_entity = (
                state.get("camera_entity_id")
                if state.get("camera_toggled")
                else None
            )
            if not switches and not camera_entity:
                continue
            switch_states = {
                entity_id: (st.state if (st := self.hass.states.get(entity_id)) else None)
                for entity_id in switches
            }
            decision = decide_manual_override(
                started_at=_parse_datetime(state.get("started_at")),
                now=datetime.now(timezone.utc),
                switch_states=switch_states,
                camera_entity_id=camera_entity,
                camera_state=(
                    camera_state.state
                    if camera_entity
                    and (camera_state := self.hass.states.get(camera_entity))
                    else None
                ),
                camera_toggled=bool(state.get("camera_toggled")),
            )
            if not decision["override"]:
                continue

            on_list = decision["on_targets"]
            _LOGGER.info(
                "Frigate Privacy pause overridden manually (%s targets on)",
                len(on_list),
            )
            self.hass.bus.async_fire(
                f"{DOMAIN}_pause_interrupted",
                {
                    "reason": "managed_target_reenabled",
                    "affected_target_count": len(on_list),
                },
            )
            await self.storage.async_mark_overridden(
                camera_id, on_switches=on_list
            )
            message = (
                "A Frigate Privacy window was interrupted because one or more "
                "managed targets were re-enabled outside the integration. The "
                "integration will not claim that privacy is enforced. An "
                "administrator can review exact details in the Frigate Privacy "
                "card."
            )
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "notification_id": _private_notification_id(
                            "override", camera_id
                        ),
                        "title": "Frigate Privacy pause interrupted",
                        "message": message,
                    },
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Could not create override notification (%s)",
                    type(err).__name__,
                )

    async def _async_refresh_override_watch(self) -> None:
        """Keep an instant state listener on every target changed by a pause."""
        paused_all = await self.storage.async_get_paused(None) or {}
        wanted: set[str] = set()
        for state in paused_all.values():
            if state.get("resume_blocked") or state.get("overridden"):
                continue
            wanted.update(state.get("switches") or [])
            if state.get("camera_toggled") and state.get("camera_entity_id"):
                wanted.add(state["camera_entity_id"])

        wanted_frozen = frozenset(wanted)
        if wanted_frozen == self._watched_targets:
            return
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        self._watched_targets = wanted_frozen
        if not wanted_frozen:
            return

        @callback
        def _on_switch_change(event: Event) -> None:
            new_state = event.data.get("new_state")
            if new_state is not None:
                self._create_task(self.async_tick())

        self._unsub_states = async_track_state_change_event(
            self.hass, sorted(wanted_frozen), _on_switch_change
        )


def schedule_in_window(schedule: dict[str, Any], now: datetime) -> bool:
    """Return True when a v4 schedule is active at local time ``now``."""
    days = set(schedule.get("days") or [])
    now_min = now.hour * 60 + now.minute
    start_min = int(schedule.get("startHour", 0)) * 60 + int(
        schedule.get("startMin", 0)
    )
    end_min = int(schedule.get("endHour", 0)) * 60 + int(schedule.get("endMin", 0))
    today = now.isoweekday()

    if end_min > start_min:
        return today in days and start_min <= now_min < end_min

    prev_day = 7 if today == 1 else today - 1
    return (today in days and now_min >= start_min) or (
        prev_day in days and now_min < end_min
    )


def async_start_scheduler(
    hass: HomeAssistant, storage: FrigatePrivacyStorage
) -> FrigatePrivacyScheduler:
    """Create and start the integration scheduler."""
    scheduler = FrigatePrivacyScheduler(hass, storage)
    scheduler.async_start()
    return scheduler


def _already_paused_by_schedule(
    state: dict[str, Any] | None, schedule_id: str
) -> bool:
    return bool(state and state.get("source") == "schedule" and state.get("schedule_id") == schedule_id)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
