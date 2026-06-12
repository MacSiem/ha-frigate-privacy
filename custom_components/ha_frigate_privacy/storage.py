"""Store-backed persistence for Frigate Privacy schedules and paused state."""

from __future__ import annotations

import asyncio
import uuid
from copy import deepcopy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


def _default_state() -> dict[str, Any]:
    return {
        "schedules": [],
        "paused": {},
    }


class FrigatePrivacyStorage:
    """Thin async wrapper around Home Assistant storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind storage to a Home Assistant instance."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> dict[str, Any]:
        """Load persisted state, creating defaults when absent."""
        async with self._lock:
            data = await self._ensure_loaded_locked()
            return deepcopy(data)

    async def async_get_state(self) -> dict[str, Any]:
        """Return the complete persisted state."""
        return await self.async_load()

    async def async_get_schedules(self) -> list[dict[str, Any]]:
        """Return persisted privacy schedules."""
        data = await self.async_load()
        return data["schedules"]

    async def async_upsert_schedule(
        self, schedule: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or update one schedule and return its normalized shape."""
        clean = self._normalize_schedule(schedule)
        async with self._lock:
            data = await self._ensure_loaded_locked()
            schedules = data["schedules"]
            for idx, existing in enumerate(schedules):
                if existing.get("id") == clean["id"]:
                    schedules[idx] = clean
                    break
            else:
                schedules.append(clean)
            await self._store.async_save(data)
            return deepcopy(clean)

    async def async_delete_schedule(self, schedule_id: str) -> bool:
        """Delete one schedule by id."""
        async with self._lock:
            data = await self._ensure_loaded_locked()
            before = len(data["schedules"])
            data["schedules"] = [
                item for item in data["schedules"] if item.get("id") != schedule_id
            ]
            changed = len(data["schedules"]) != before
            if changed:
                await self._store.async_save(data)
            return changed

    async def async_replace_schedules(
        self, schedules: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Replace all schedules with normalized values."""
        clean = [self._normalize_schedule(item) for item in schedules]
        async with self._lock:
            data = await self._ensure_loaded_locked()
            data["schedules"] = clean
            await self._store.async_save(data)
            return deepcopy(clean)

    async def async_get_paused(
        self, camera_id: str | None = None
    ) -> dict[str, Any] | None:
        """Return one paused state or all paused states."""
        data = await self.async_load()
        if camera_id is None:
            return data["paused"]
        paused = data["paused"].get(camera_id)
        return deepcopy(paused) if paused else None

    async def async_set_paused(
        self, camera_id: str, state: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist paused state for one camera."""
        if not camera_id:
            raise ValueError("camera_id is required")
        async with self._lock:
            data = await self._ensure_loaded_locked()
            clean = deepcopy(state)
            clean["camera_id"] = camera_id
            clean["active"] = True
            data["paused"][camera_id] = clean
            await self._store.async_save(data)
            return deepcopy(clean)

    async def async_clear_paused(self, camera_id: str) -> bool:
        """Clear paused state for one camera."""
        async with self._lock:
            data = await self._ensure_loaded_locked()
            existed = camera_id in data["paused"]
            data["paused"].pop(camera_id, None)
            if existed:
                await self._store.async_save(data)
            return existed

    async def async_mark_resume_blocked(
        self,
        camera_id: str,
        *,
        reason: str,
        failed: list[str],
        unavailable: list[str],
    ) -> dict[str, Any] | None:
        """Record that automatic resume is blocked and paused state remains."""
        async with self._lock:
            data = await self._ensure_loaded_locked()
            paused = data["paused"].get(camera_id)
            if not paused:
                return None
            paused["resume_blocked"] = True
            paused["resume_blocked_reason"] = reason
            paused["resume_failed"] = list(failed)
            paused["resume_unavailable"] = list(unavailable)
            await self._store.async_save(data)
            return deepcopy(paused)

    async def _ensure_loaded_locked(self) -> dict[str, Any]:
        """Load storage while the caller holds the lock."""
        if self._data is None:
            loaded = await self._store.async_load()
            if not isinstance(loaded, dict):
                loaded = {}
            self._data = _default_state()
            self._deep_merge(self._data, loaded)
            self._data["schedules"] = [
                self._normalize_schedule(item)
                for item in self._data.get("schedules") or []
                if isinstance(item, dict)
            ]
            paused = self._data.get("paused")
            self._data["paused"] = paused if isinstance(paused, dict) else {}
        return self._data

    @staticmethod
    def _normalize_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
        """Normalize the v4 card schedule shape and keep unknown fields out."""
        if not isinstance(schedule, dict):
            raise ValueError("schedule must be an object")
        days = schedule.get("days") or []
        clean_days = sorted(
            {
                max(1, min(7, int(day)))
                for day in days
                if str(day).strip()
            }
        )
        if not clean_days:
            clean_days = [1, 2, 3, 4, 5]
        return {
            "id": str(schedule.get("id") or uuid.uuid4().hex),
            "enabled": schedule.get("enabled") is not False,
            "days": clean_days,
            "startHour": max(0, min(23, int(schedule.get("startHour", 18)))),
            "startMin": max(0, min(59, int(schedule.get("startMin", 0)))),
            "endHour": max(0, min(23, int(schedule.get("endHour", 20)))),
            "endMin": max(0, min(59, int(schedule.get("endMin", 0)))),
            "repeat": schedule.get("repeat") is not False,
            "label": str(schedule.get("label") or ""),
        }

    @classmethod
    def _deep_merge(cls, target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                cls._deep_merge(target[key], value)
            else:
                target[key] = deepcopy(value)
