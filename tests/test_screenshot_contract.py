"""Source-bound, privacy-safe public screenshot contract."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "screenshots" / "manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _image_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        assert raw[12:16] == b"IHDR"
        return struct.unpack(">II", raw[16:24])
    assert raw.startswith(b"\xff\xd8"), "Expected an original PNG or JPEG capture"
    offset = 2
    while offset < len(raw):
        assert raw[offset] == 255
        marker = raw[offset + 1]
        offset += 2
        size = int.from_bytes(raw[offset:offset + 2], "big")
        assert size >= 2
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", raw[offset + 3:offset + 7])
            return width, height
        offset += size
    raise AssertionError("JPEG has no frame dimensions")


def test_public_screenshots_are_source_bound_and_synthetic() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = ROOT / manifest["source"]["path"]
    harness = ROOT / manifest["harness"]["path"]

    assert _sha256(source) == manifest["source"]["sha256"]
    assert _sha256(harness) == manifest["harness"]["sha256"]
    assert 'data-fixture="privacy-safe-generic-home"' in harness.read_text()
    assert manifest["privacy"] == {
        "synthetic_only": True,
        "ocr_reviewed": True,
        "external_requests": False,
    }

    for image in manifest["images"]:
        path = ROOT / image["path"]
        assert _sha256(path) == image["sha256"]
        assert _image_dimensions(path) == (image["width"], image["height"])
