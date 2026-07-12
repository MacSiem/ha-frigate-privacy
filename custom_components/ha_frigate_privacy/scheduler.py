"""Server-side schedule application for Frigate Privacy."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)

from .const import DOMAIN
from .control import async_pause_cameras, async_resume_camera, discover_frigate_cameras
from .failsafe import decide_manual_override
from .storage import FrigatePrivacyStorage

_LOGGER = logging.getLogger(__name__)


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
        self._watched_switches: frozenset[str] = frozenset()

    def async_start(self) -> None:
        """Start minute ticks and re-check on HA start."""
        if self._unsub_time is None:
            self._unsub_time = async_track_time_change(
                self.hass, self._handle_time, second=0
            )
        if self.hass.is_running:
            self.hass.async_create_task(self.async_tick())
        else:
            self._unsub_start = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._handle_started
            )

    def async_stop(self) -> None:
        """Stop scheduled callbacks."""
        if self._unsub_time:
            self._unsub_time()
            self._unsub_time = None
        if self._unsub_start:
            self._unsub_start()
            self._unsub_start = None
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        self._watched_switches = frozenset()

    @callback
    def _handle_started(self, _: Event) -> None:
        """Re-arm schedule state after Home Assistant startup."""
        self.hass.async_create_task(self.async_tick())

    @callback
    def _handle_time(self, now: datetime) -> None:
        """Schedule a tick from async_track_time_change."""
        self.hass.async_create_task(self.async_tick(now))

    async def async_tick(self, now: datetime | None = None) -> None:
        """Apply active windows and exit inactive windows."""
        now = now or datetime.now().astimezone()
        schedules = await self.storage.async_get_schedules()
        cameras = discover_frigate_cameras(self.hass)
        camera_ids = [item["camera_id"] for item in cameras]
        if not camera_ids:
            return

        active = {
            schedule["id"]: schedule
            for schedule in schedules
            if schedule.get("enabled") and schedule_in_window(schedule, now)
        }

        paused_all = await self.storage.async_get_paused(None) or {}
        paused_by_schedule = {
            camera_id: state
            for camera_id, state in paused_all.items()
            if state.get("source") == "schedule"
        }

        for schedule_id, schedule in active.items():
            refs = [
                camera_id
                for camera_id in camera_ids
                if not _already_paused_by_schedule(
                    paused_all.get(camera_id), schedule_id
                )
            ]
            if refs:
                _LOGGER.debug(
                    "Applying Frigate Privacy schedule %s to %s",
                    schedule_id,
                    refs,
                )
                await async_pause_cameras(
                    self.hass,
                    self.storage,
                    refs,
                    stream_type="all",
                    source="schedule",
                    schedule_id=schedule_id,
                )

        active_ids = set(active)
        for camera_id, state in paused_by_schedule.items():
            if state.get("resume_blocked"):
                continue
            if state.get("schedule_id") in active_ids:
                continue
            await async_resume_camera(
                self.hass, self.storage, camera_id, automatic=True
            )

        paused_all = await self.storage.async_get_paused(None) or {}
        for camera_id, state in paused_all.items():
            if state.get("source") == "schedule" or state.get("resume_blocked"):
                continue
            ends_at = _parse_datetime(state.get("ends_at"))
            if ends_at and datetime.now(timezone.utc) >= ends_at:
                await async_resume_camera(
                    self.hass, self.storage, camera_id, automatic=True
                )

        await self._async_handle_manual_overrides()
        await self._async_refresh_override_watch()

    async def _async_handle_manual_overrides(self) -> None:
        """Detect pauses whose switches were re-enabled outside the integration.

        Manual pauses are cancelled (remaining switches restored, entry
        cleared). Schedule pauses are only marked ``overridden`` — cancelling
        them would make the next tick re-apply the window and fight the user.
        Both variants notify, so the UI and the user reflect reality instead
        of a phantom "paused" state.
        """
        paused_all = await self.storage.async_get_paused(None) or {}
        for camera_id, state in paused_all.items():
            if state.get("resume_blocked") or state.get("overridden"):
                continue
            switches = list(state.get("switches") or [])
            if not switches:
                continue
            switch_states = {
                entity_id: (st.state if (st := self.hass.states.get(entity_id)) else None)
                for entity_id in switches
            }
            decision = decide_manual_override(
                started_at=_parse_datetime(state.get("started_at")),
                now=datetime.now(timezone.utc),
                switch_states=switch_states,
            )
            if not decision["override"]:
                continue

            name = state.get("name") or camera_id
            on_list = decision["on_switches"]
            _LOGGER.info(
                "Frigate Privacy pause for %s overridden manually (%s on): %s",
                camera_id,
                len(on_list),
                on_list,
            )
            self.hass.bus.async_fire(
                f"{DOMAIN}_pause_interrupted",
                {
                    "camera_id": camera_id,
                    "source": state.get("source"),
                    "on_switches": on_list,
                },
            )
            if state.get("source") == "schedule":
                await self.storage.async_mark_overridden(
                    camera_id, on_switches=on_list
                )
                message = (
                    f"The scheduled privacy window for {name} is no longer "
                    f"enforced: {len(on_list)} switch(es) were re-enabled "
                    f"outside Frigate Privacy ({', '.join(on_list)}). The "
                    "window will not be re-applied automatically; re-pause "
                    "from the card if this was accidental."
                )
            else:
                await async_resume_camera(
                    self.hass, self.storage, camera_id, automatic=True
                )
                message = (
                    f"The privacy pause for {name} was ended early: "
                    f"{len(on_list)} switch(es) were re-enabled outside "
                    f"Frigate Privacy ({', '.join(on_list)}). The remaining "
                    "switches were restored and the pause was cleared."
                )
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "notification_id": f"{DOMAIN}_override_{camera_id}",
                        "title": "Frigate Privacy pause interrupted",
                        "message": message,
                    },
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not create override notification: %s", err)

    async def _async_refresh_override_watch(self) -> None:
        """Keep an instant state listener on switches of active pauses."""
        paused_all = await self.storage.async_get_paused(None) or {}
        wanted: set[str] = set()
        for state in paused_all.values():
            if state.get("resume_blocked") or state.get("overridden"):
                continue
            wanted.update(state.get("switches") or [])

        wanted_frozen = frozenset(wanted)
        if wanted_frozen == self._watched_switches:
            return
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        self._watched_switches = wanted_frozen
        if not wanted_frozen:
            return

        @callback
        def _on_switch_change(event: Event) -> None:
            new_state = event.data.get("new_state")
            if new_state is not None and new_state.state == "on":
                self.hass.async_create_task(self.async_tick())

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
