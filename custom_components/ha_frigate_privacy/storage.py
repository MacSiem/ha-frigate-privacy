"""Store-backed persistence for Frigate Privacy schedules and paused state."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from copy import deepcopy
from typing import Any
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
try:
    from homeassistant.core import CoreState
except ImportError:  # lightweight synthetic fixtures; HA provides the real enum
    CoreState = None
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .periods import capture, read_history, utc
from .replay import (
    ReplayFilterError,
    normalize_replay_filter,
    replay_filter_add,
    replay_filter_contains,
)


def _default_state() -> dict[str, Any]:
    return {
        "schedules": [],
        "schedule_operations": [],
        "schedule_operation_filter": normalize_replay_filter(None),
        "camera_operation_filters": {},
        "replay_integrity": {"state": "valid", "errors": []},
        "paused": {},
    }


class StorageWriteError(RuntimeError):
    """Home Assistant reported a storage write failure after swallowing it."""


class ReplayIntegrityError(ValueError):
    """Persisted replay evidence is corrupt, so mutations must stop."""


class _ConfirmedStore(Store):
    """Turn HA Store's logged write failures back into transactional failures.

    Home Assistant's ``Store._async_handle_write_data`` intentionally catches
    ``WriteError`` and serialization errors after logging them. Intercepting
    the lower write method preserves that error until ``async_save`` returns,
    so callers never proceed as if a durable privacy transition succeeded.
    """

    _last_write_error: Exception | None

    def __init__(self, hass: HomeAssistant, *args: Any, **kwargs: Any) -> None:
        self._privacy_hass = hass
        super().__init__(hass, *args, **kwargs)

    async def async_save(self, data: dict[str, Any]) -> None:
        # HA may silently defer/skip a write during shutdown. Durable state
        # requires actual lower-level completion, not just async_save returning.
        if getattr(self._privacy_hass, "state", None) == (CoreState.stopping if CoreState else "stopping"):
            raise StorageWriteError("privacy state write skipped during shutdown")
        self._last_write_error = None
        self._write_confirmed = False
        await super().async_save(data)
        if error := self._last_write_error:
            raise StorageWriteError("privacy state was not durably saved") from error
        if not self._write_confirmed:
            raise StorageWriteError("privacy state write was not confirmed")

    async def _async_write_data(self, *args: Any, **kwargs: Any) -> None:
        try:
            # HA 2025.2 passes (path, data); newer cores pass only data.
            # Forward the core's arguments without weakening error detection.
            await super()._async_write_data(*args, **kwargs)
            self._write_confirmed = True
        except Exception as err:
            # Re-raise so Store retains its normal logging/handling behavior;
            # async_save above converts only its swallowed outcome to a failure.
            self._last_write_error = err
            raise


class FrigatePrivacyStorage:
    """Thin async wrapper around Home Assistant storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind storage to a Home Assistant instance."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = _ConfirmedStore(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            private=True,
            atomic_writes=True,
        )
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] | None = None
        self._period_durability = "not_written"

    async def async_load(self) -> dict[str, Any]:
        """Load persisted state, creating defaults when absent."""
        async with self._lock:
            data = await self._ensure_loaded_locked()
            return deepcopy(data)

    async def async_get_state(self) -> dict[str, Any]:
        """Return active privacy state plus the last terminal operation."""
        data = await self.async_load()
        active = {
            camera_id: state
            for camera_id, state in data["paused"].items()
            if state.get("active", True)
        }
        terminal = {
            camera_id: state
            for camera_id, state in data["paused"].items()
            if not state.get("active", True)
        }
        return {
            "schedules": data["schedules"],
            "paused": active,
            "last_operations": terminal,
            "last_outcome": "error" if self._period_durability == "save_failed" else data.get("last_outcome"),
        }

    async def async_record_outcome(self, outcome: str) -> None:
        """Persist the completed aggregate result, retaining unknown on fresh installs."""
        if outcome not in {"confirmed", "partial", "error"}:
            raise ValueError("invalid control outcome")
        async with self._lock:
            data = await self._ensure_loaded_locked()
            if data.get("last_outcome") == outcome:
                return
            previous = deepcopy(data)
            data["last_outcome"] = outcome
            await self._save_locked(data, previous)

    async def async_get_periods(self, *, days: int = 30) -> dict[str, Any]:
        """Project already loaded state without save, load, probe or migration."""
        if days not in {7, 30}:
            raise ValueError("invalid history range")
        async with self._lock:
            if self._data is None:
                return {"schema": 1, "status": "unavailable", "periods": [],
                        "durability": "not_loaded", "days": days}
            result = read_history(self._data.get("privacy_periods"),
                                  self._data.get("paused", {}),
                                  datetime.now(timezone.utc), days)
            result["durability"] = self._period_durability
            return result

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
            previous = deepcopy(data)
            schedules = data["schedules"]
            for idx, existing in enumerate(schedules):
                if existing.get("id") == clean["id"]:
                    schedules[idx] = clean
                    break
            else:
                schedules.append(clean)
            await self._save_locked(data, previous)
            return deepcopy(clean)

    async def async_delete_schedule(self, schedule_id: str) -> bool:
        """Delete one schedule by id."""
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            before = len(data["schedules"])
            data["schedules"] = [
                item for item in data["schedules"] if item.get("id") != schedule_id
            ]
            changed = len(data["schedules"]) != before
            if changed:
                await self._save_locked(data, previous)
            return changed

    async def async_replace_schedules(
        self, schedules: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Replace all schedules with normalized values."""
        if len(schedules) > 256:
            raise ValueError("too many schedules")
        clean = [self._normalize_schedule(item) for item in schedules]
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            data["schedules"] = clean
            await self._save_locked(data, previous)
            return deepcopy(clean)

    async def async_apply_schedule_operation(
        self,
        *,
        operation_id: str | None,
        action: str,
        schedule: dict[str, Any] | None = None,
        schedule_id: str | None = None,
        schedules: list[dict[str, Any]] | None = None,
        request_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply one absolute schedule mutation with bounded idempotency."""
        if operation_id and not 1 <= len(operation_id) <= 128:
            raise ValueError("invalid operation id")
        if action not in {"upsert", "delete", "replace_all", "clear"}:
            raise ValueError("invalid schedule action")

        if action == "upsert" and (
            not isinstance(schedule, dict)
            or not isinstance(schedule.get("id"), str)
            or not schedule["id"].strip()
        ):
            raise ValueError("schedule id is required")
        if action == "delete" and not schedule_id:
            raise ValueError("schedule id is required")
        clean_schedule = (
            self._normalize_schedule(schedule) if schedule is not None else None
        )
        clean_schedules = (
            [self._normalize_schedule(item) for item in schedules]
            if schedules is not None
            else None
        )
        if clean_schedules is not None and len(clean_schedules) > 256:
            raise ValueError("too many schedules")
        normalized_request = {
            "action": action,
            "schedule": clean_schedule if action == "upsert" else None,
            "schedule_id": schedule_id if action == "delete" else None,
            "schedules": clean_schedules if action == "replace_all" else None,
        }
        request_fingerprint = hashlib.sha256(
            json.dumps(
                normalized_request,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            self._assert_replay_integrity(data)
            operations = data.setdefault("schedule_operations", [])
            if operation_id:
                for prior in reversed(operations):
                    if prior.get("id") != operation_id:
                        continue
                    if prior.get("action") != action:
                        raise ValueError("operation id already used")
                    if prior.get("request_fingerprint") not in {
                        None,
                        request_fingerprint,
                    }:
                        raise ValueError("operation id payload mismatch")
                    return deepcopy(prior["result"])
                if replay_filter_contains(
                    data.get("schedule_operation_filter"), action, operation_id
                ):
                    raise ValueError("operation id result expired")
                data["schedule_operation_filter"] = replay_filter_add(
                    data.get("schedule_operation_filter"),
                    action,
                    operation_id,
                    seed_history=operations,
                )

            if action == "upsert":
                if clean_schedule is None:
                    raise ValueError("schedule is required")
                for index, existing in enumerate(data["schedules"]):
                    if existing.get("id") == clean_schedule["id"]:
                        data["schedules"][index] = clean_schedule
                        break
                else:
                    data["schedules"].append(clean_schedule)
                result = {"schedule": deepcopy(clean_schedule)}
            elif action == "delete":
                before = len(data["schedules"])
                data["schedules"] = [
                    item
                    for item in data["schedules"]
                    if item.get("id") != schedule_id
                ]
                result = {"deleted": len(data["schedules"]) != before}
            elif action == "replace_all":
                data["schedules"] = clean_schedules or []
                result = {"schedules": deepcopy(data["schedules"])}
            else:
                data["schedules"] = []
                result = {"schedules": []}

            if operation_id:
                operations.append(
                    {
                        "id": operation_id,
                        "action": action,
                        "request_user_id": request_user_id,
                        "request_fingerprint": request_fingerprint,
                        "result": deepcopy(result),
                    }
                )
                data["schedule_operations"] = operations[-64:]
            await self._save_locked(data, previous)
            return result

    async def async_reserve_camera_operation(
        self,
        camera_id: str,
        action: str,
        operation_id: str,
        *,
        history: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Persist a monotonic camera-operation tombstone before side effects."""
        if not camera_id or not operation_id or action not in {"pause", "resume", "extend"}:
            raise ValueError("invalid camera operation")
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            self._assert_replay_integrity(data)
            filters = data.setdefault("camera_operation_filters", {})
            current = filters.get(camera_id)
            if replay_filter_contains(current, action, operation_id):
                return False
            filters[camera_id] = replay_filter_add(
                current,
                action,
                operation_id,
                seed_history=history or [],
            )
            await self._save_locked(data, previous)
            return True

    async def async_get_paused(
        self,
        camera_id: str | None = None,
        *,
        include_inactive: bool = False,
    ) -> dict[str, Any] | None:
        """Return active privacy records, optionally including terminal state."""
        data = await self.async_load()
        if camera_id is None:
            records = data["paused"]
            if include_inactive:
                return records
            return {
                key: value
                for key, value in records.items()
                if value.get("active", True)
            }
        paused = data["paused"].get(camera_id)
        if paused and not include_inactive and not paused.get("active", True):
            return None
        return deepcopy(paused) if paused else None

    async def async_get_record(self, camera_id: str) -> dict[str, Any] | None:
        """Return the latest active or terminal record for idempotency/audit."""
        return await self.async_get_paused(camera_id, include_inactive=True)

    async def async_set_paused(
        self, camera_id: str, state: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist paused state for one camera."""
        if not camera_id:
            raise ValueError("camera_id is required")
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            clean = deepcopy(state)
            clean["camera_id"] = camera_id
            clean.setdefault("phase", "paused")
            clean["active"] = clean["phase"] != "active"
            data["paused"][camera_id] = clean
            await self._save_locked(data, previous)
            return deepcopy(clean)

    async def async_transition_paused(
        self,
        camera_id: str,
        phase: str,
        **updates: Any,
    ) -> dict[str, Any] | None:
        """Atomically update one persisted state-machine record."""
        if phase not in {"pausing", "paused", "resuming", "partial", "error"}:
            raise ValueError("invalid transition phase")
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            paused = data["paused"].get(camera_id)
            if not paused:
                return None
            paused.update(deepcopy(updates))
            paused["phase"] = phase
            paused["active"] = True
            await self._save_locked(data, previous)
            return deepcopy(paused)

    async def async_clear_paused(self, camera_id: str) -> bool:
        """Delete one record (legacy cleanup only; normal resume persists active)."""
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            existed = camera_id in data["paused"]
            data["paused"].pop(camera_id, None)
            if existed:
                await self._save_locked(data, previous)
            return existed

    async def async_mark_active(
        self,
        camera_id: str,
        **updates: Any,
    ) -> dict[str, Any] | None:
        """Persist a verified terminal active state without losing evidence."""
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            paused = data["paused"].get(camera_id)
            if not paused:
                return None
            paused.update(deepcopy(updates))
            paused["phase"] = "active"
            paused["active"] = False
            paused["desired_state"] = "active"
            # Only this observed terminal transition may record an actual end.
            paused["period_ended_at"] = updates.get("observed_at")
            paused["period_end_reason"] = paused.get("resume_reason") or "unknown"
            await self._save_locked(data, previous)
            return deepcopy(paused)

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
            previous = deepcopy(data)
            paused = data["paused"].get(camera_id)
            if not paused:
                return None
            paused["resume_blocked"] = True
            paused["resume_blocked_reason"] = reason
            paused["resume_failed"] = list(failed)
            paused["resume_unavailable"] = list(unavailable)
            paused["phase"] = "error"
            paused["active"] = True
            await self._save_locked(data, previous)
            return deepcopy(paused)

    async def async_mark_overridden(
        self,
        camera_id: str,
        *,
        on_switches: list[str],
    ) -> dict[str, Any] | None:
        """Record that a pause was overridden manually (switches re-enabled).

        Used for schedule-sourced pauses: the entry is kept so the scheduler
        does not immediately re-apply the window against the user's explicit
        choice, but the state honestly reflects that privacy is no longer
        enforced.
        """
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            paused = data["paused"].get(camera_id)
            if not paused:
                return None
            paused["overridden"] = True
            paused["overridden_switches"] = list(on_switches)
            paused["override_active_schedule_ids"] = list(
                paused.get("active_schedule_ids")
                or (
                    [paused["schedule_id"]]
                    if paused.get("schedule_id")
                    else []
                )
            )
            paused["phase"] = "active"
            paused["active"] = False
            paused["desired_state"] = "active"
            paused["reason"] = "manual_override"
            observed = datetime.now(timezone.utc).isoformat()
            paused["observed_at"] = observed
            paused["period_ended_at"] = observed
            paused["period_end_reason"] = "manual_override"
            paused["period_restore_proof"] = {}
            await self._save_locked(data, previous)
            return deepcopy(paused)

    async def async_release_schedule_override(
        self,
        camera_id: str,
    ) -> dict[str, Any] | None:
        """Release a terminal override after its schedule coverage has ended.

        The terminal evidence remains available to the administrator, but a
        later recurrence of the schedule is allowed to create a fresh pause.
        """
        async with self._lock:
            data = await self._ensure_loaded_locked()
            previous = deepcopy(data)
            record = data["paused"].get(camera_id)
            if (
                not record
                or record.get("source") != "schedule"
                or not record.get("overridden")
                or record.get("active", True)
            ):
                return deepcopy(record) if record else None
            record["overridden"] = False
            record["override_released"] = True
            record["override_active_schedule_ids"] = []
            await self._save_locked(data, previous)
            return deepcopy(record)

    @staticmethod
    def _assert_replay_integrity(data: dict[str, Any]) -> None:
        """Refuse replay-protected mutation while evidence is not trustworthy."""
        integrity = data.get("replay_integrity")
        if not isinstance(integrity, dict) or integrity.get("state") != "valid":
            raise ReplayIntegrityError("replay integrity evidence is corrupt")

    async def _save_locked(
        self,
        data: dict[str, Any],
        previous: dict[str, Any],
    ) -> None:
        """Save while preserving the last durable in-memory snapshot on failure."""
        try:
            # Preserve pause identity when resume advances the control generation.
            for camera, record in data.get("paused", {}).items():
                old = previous.get("paused", {}).get(camera, {})
                if record != old and "period_generation" not in record:
                    record["period_generation"] = (
                        old.get("period_generation")
                        if old and old.get("started_at") == record.get("started_at")
                        else record.get("generation")
                    )
                if record != old and "period_started_at" not in record:
                    record["period_started_at"] = (
                        old.get("period_started_at", utc(old.get("started_at"), datetime.now(timezone.utc)))
                        if old and old.get("started_at") == record.get("started_at")
                        else utc(record.get("started_at"), datetime.now(timezone.utc))
                    )
            # Publish only completed, durably saved control outcomes. Reads and
            # intent reservations must never manufacture a successful result.
            for camera, record in data.get("paused", {}).items():
                old = previous.get("paused", {}).get(camera, {})
                phase = record.get("phase")
                if record != old and phase in {"paused", "active", "partial", "error"}:
                    data["last_outcome"] = (
                        "confirmed" if phase in {"paused", "active"}
                        else "partial" if phase == "partial" else "error"
                    )
            capture_succeeded = False
            if data.get("paused") != previous.get("paused"):
                try:
                    candidate = capture(data.get("privacy_periods"),
                                        previous.get("paused", {}), data.get("paused", {}),
                                        datetime.now(timezone.utc))
                except (ValueError, TypeError, OverflowError):
                    # Never weaken control/recovery because a projection cannot
                    # be captured. Keep prior history intact and expose failure.
                    self._period_durability = "capture_failed"
                else:
                    data["privacy_periods"] = candidate
                    capture_succeeded = True
            await self._store.async_save(data)
            if capture_succeeded or self._period_durability != "capture_failed":
                self._period_durability = "confirmed"
        except asyncio.CancelledError:
            self._data = previous
            self._period_durability = "save_failed"
            raise
        except Exception:
            self._data = previous
            self._period_durability = "save_failed"
            raise

    async def _ensure_loaded_locked(self) -> dict[str, Any]:
        """Load storage while the caller holds the lock."""
        if self._data is None:
            loaded = await self._store.async_load()
            if not isinstance(loaded, dict):
                loaded = {}
            loaded = deepcopy(loaded)
            self._period_durability = "loaded"
            if not isinstance(loaded.get("schedules"), list):
                loaded["schedules"] = []
            if not isinstance(loaded.get("schedule_operations"), list):
                loaded["schedule_operations"] = []
            if not isinstance(loaded.get("paused"), dict):
                loaded["paused"] = {}
            self._data = _default_state()
            self._deep_merge(self._data, loaded)
            self._data["schedules"] = [
                self._normalize_schedule(item)
                for item in (self._data.get("schedules") or [])[:256]
                if isinstance(item, dict)
            ]
            schedule_operations = self._data.get("schedule_operations")
            self._data["schedule_operations"] = (
                [
                    deepcopy(item)
                    for item in schedule_operations[-64:]
                    if isinstance(item, dict)
                    and isinstance(item.get("id"), str)
                    and isinstance(item.get("result"), dict)
                ]
                if isinstance(schedule_operations, list)
                else []
            )
            self._normalize_replay_state(loaded)
            paused = self._data.get("paused")
            self._data["paused"] = {
                camera_id: deepcopy(record)
                for camera_id, record in (
                    paused.items() if isinstance(paused, dict) else []
                )
                if isinstance(camera_id, str) and isinstance(record, dict)
            }
            for camera_id, state in self._data["paused"].items():
                if not isinstance(state, dict):
                    self._data["paused"][camera_id] = {
                        "camera_id": camera_id,
                        "phase": "error",
                        "active": True,
                        "reason": "invalid_persisted_state",
                    }
                    continue
                state.setdefault("camera_id", camera_id)
                state.setdefault("phase", "paused")
                if state.get("overridden"):
                    # Earlier builds only set the marker and continued to
                    # advertise enforced privacy. Preserve evidence but make
                    # this a terminal active/manual-override record.
                    state["phase"] = "active"
                    state["active"] = False
                    state["desired_state"] = "active"
                    state["reason"] = "manual_override"
                    state.setdefault(
                        "override_active_schedule_ids",
                        list(
                            state.get("active_schedule_ids")
                            or (
                                [state["schedule_id"]]
                                if state.get("schedule_id")
                                else []
                            )
                        ),
                    )
                    continue
                state["active"] = state["phase"] != "active"
        return self._data

    def _normalize_replay_state(self, loaded: dict[str, Any]) -> None:
        """Validate replay fields and retain redacted evidence on corruption."""
        assert self._data is not None
        errors: list[dict[str, str]] = []

        def capture(scope: str, value: Any, error: ReplayFilterError) -> None:
            evidence = repr(value)[:4096]
            digest = hashlib.sha256(
                evidence.encode("utf-8", "backslashreplace")
            ).hexdigest()
            errors.append(
                {
                    "scope": scope,
                    "code": type(error).__name__,
                    "digest": digest,
                }
            )

        if "schedule_operation_filter" not in loaded:
            self._data["schedule_operation_filter"] = normalize_replay_filter(None)
        else:
            raw_schedule_filter = loaded["schedule_operation_filter"]
            try:
                self._data["schedule_operation_filter"] = normalize_replay_filter(
                    raw_schedule_filter
                )
            except ReplayFilterError as error:
                capture("schedule_operation_filter", raw_schedule_filter, error)

        if "camera_operation_filters" not in loaded:
            self._data["camera_operation_filters"] = {}
        elif not isinstance(loaded["camera_operation_filters"], dict):
            capture(
                "camera_operation_filters",
                loaded["camera_operation_filters"],
                ReplayFilterError("camera replay filters must be an object"),
            )
        else:
            filters: dict[str, dict[str, Any]] = {}
            for camera_id, raw_filter in loaded["camera_operation_filters"].items():
                if not isinstance(camera_id, str) or not camera_id:
                    capture(
                        "camera_operation_filters",
                        camera_id,
                        ReplayFilterError("camera replay filter id is invalid"),
                    )
                    continue
                try:
                    filters[camera_id] = normalize_replay_filter(raw_filter)
                except ReplayFilterError as error:
                    capture(f"camera_operation_filters.{camera_id}", raw_filter, error)
            self._data["camera_operation_filters"] = filters

        self._data["replay_integrity"] = {
            "state": "corrupt" if errors else "valid",
            "errors": errors,
        }

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
            "id": str(schedule.get("id") or uuid.uuid4().hex)[:128],
            "enabled": schedule.get("enabled") is not False,
            "days": clean_days,
            "startHour": max(0, min(23, int(schedule.get("startHour", 18)))),
            "startMin": max(0, min(59, int(schedule.get("startMin", 0)))),
            "endHour": max(0, min(23, int(schedule.get("endHour", 20)))),
            "endMin": max(0, min(59, int(schedule.get("endMin", 0)))),
            "repeat": schedule.get("repeat") is not False,
            "label": str(schedule.get("label") or "")[:120],
        }

    @classmethod
    def _deep_merge(cls, target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                cls._deep_merge(target[key], value)
            else:
                target[key] = deepcopy(value)
