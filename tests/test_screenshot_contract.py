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


def _png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert raw[12:16] == b"IHDR"
    return struct.unpack(">II", raw[16:24])


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
        assert _png_dimensions(path) == (image["width"], image["height"])
