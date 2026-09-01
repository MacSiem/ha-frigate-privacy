"""Bounded, fail-closed replay tombstones for privacy operations.

The persisted filter is deliberately monotonic. A request once admitted must
never become admissible again merely because its exact result was evicted.
When the bounded filter reaches its explicit capacity, new mutations stop
before side effects instead of silently rotating away replay evidence.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

REPLAY_FILTER_VERSION = 2
REPLAY_FILTER_BITS = 65_536
REPLAY_FILTER_BYTES = REPLAY_FILTER_BITS // 8
REPLAY_FILTER_HASHES = 7
# At this bound the Bloom false-positive probability remains very low. More
# importantly, refusing additional mutations has no false-negative path.
REPLAY_FILTER_MAX_ACCEPTED = 4_096


class ReplayFilterError(ValueError):
    """A persisted replay filter is malformed or unsupported."""


class ReplayFilterSaturatedError(ReplayFilterError):
    """A valid monotonic replay filter cannot safely admit another id."""


def _empty_filter() -> bytearray:
    return bytearray(REPLAY_FILTER_BYTES)


def _decode_bits(value: Any) -> bytearray:
    if not isinstance(value, str):
        raise ReplayFilterError("replay filter bits must be a base64 string")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError, binascii.Error) as err:
        raise ReplayFilterError("replay filter bits are not valid base64") from err
    if len(decoded) != REPLAY_FILTER_BYTES:
        raise ReplayFilterError("replay filter has an invalid bit length")
    return bytearray(decoded)


def _encode_bits(bits: bytearray) -> str:
    return base64.b64encode(bits).decode("ascii")


def new_replay_filter() -> dict[str, Any]:
    """Return a new empty replay filter for a genuinely fresh install."""
    return {
        "version": REPLAY_FILTER_VERSION,
        "bits": _encode_bits(_empty_filter()),
        "accepted": 0,
    }


def normalize_replay_filter(value: Any) -> dict[str, Any]:
    """Validate and canonicalize a persisted filter without resetting corruption.

    ``None`` is intentionally the only empty value: it represents a missing
    field from a clean install. A valid v1 string is migrated in memory to the
    v2 envelope; malformed present values always raise so their caller can
    retain integrity evidence and block mutation.
    """
    if value is None:
        return new_replay_filter()

    # v1 stored the raw Bloom bitset. Keep every bit during migration so an old
    # operation remains rejected even after the exact ledger has rolled over.
    if isinstance(value, str):
        return {
            "version": REPLAY_FILTER_VERSION,
            "bits": _encode_bits(_decode_bits(value)),
            "accepted": 0,
        }

    if not isinstance(value, Mapping):
        raise ReplayFilterError("replay filter must be an object")
    if set(value) != {"version", "bits", "accepted"}:
        raise ReplayFilterError("replay filter has an unexpected schema")
    if value.get("version") != REPLAY_FILTER_VERSION:
        raise ReplayFilterError("replay filter version is unsupported")
    accepted = value.get("accepted")
    if isinstance(accepted, bool) or not isinstance(accepted, int):
        raise ReplayFilterError("replay filter accepted count is invalid")
    if not 0 <= accepted <= REPLAY_FILTER_MAX_ACCEPTED:
        raise ReplayFilterError("replay filter accepted count is out of range")
    return {
        "version": REPLAY_FILTER_VERSION,
        "bits": _encode_bits(_decode_bits(value.get("bits"))),
        "accepted": accepted,
    }


def _positions(action: str, operation_id: str) -> tuple[int, ...]:
    digest = hashlib.sha256(
        f"{action}\0{operation_id}".encode("utf-8", errors="strict")
    ).digest()
    return tuple(
        int.from_bytes(digest[offset : offset + 4], "big") % REPLAY_FILTER_BITS
        for offset in range(0, REPLAY_FILTER_HASHES * 4, 4)
    )


def replay_filter_contains(value: Any, action: str, operation_id: str) -> bool:
    """Return whether an operation was probably accepted before.

    Bloom false positives fail closed. Invalid state is never treated as an
    empty filter and therefore cannot reopen a replay window.
    """
    bits = _decode_bits(normalize_replay_filter(value)["bits"])
    return all(
        bits[position // 8] & (1 << (position % 8))
        for position in _positions(action, operation_id)
    )


def replay_filter_add(
    value: Any,
    action: str,
    operation_id: str,
    *,
    seed_history: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Add one operation without discarding any earlier replay evidence."""
    current = normalize_replay_filter(value)
    if current["accepted"] >= REPLAY_FILTER_MAX_ACCEPTED:
        raise ReplayFilterSaturatedError("replay filter is saturated")
    bits = _decode_bits(current["bits"])

    def add(item_action: str, item_id: str) -> None:
        for position in _positions(item_action, item_id):
            bits[position // 8] |= 1 << (position % 8)

    for item in seed_history:
        item_id = item.get("id")
        item_action = item.get("action")
        if isinstance(item_id, str) and isinstance(item_action, str):
            add(item_action, item_id)
    add(action, operation_id)
    return {
        "version": REPLAY_FILTER_VERSION,
        "bits": _encode_bits(bits),
        "accepted": current["accepted"] + 1,
    }
