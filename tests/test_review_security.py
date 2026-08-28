"""Regression checks for security-sensitive review fixes."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = ROOT / "custom_components/ha_frigate_privacy/__init__.py"
CARD_PATH = (
    ROOT
    / "custom_components/ha_frigate_privacy/www/ha-frigate-privacy-card.js"
)


def _function(tree: ast.AST, name: str) -> ast.AsyncFunctionDef:
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )


def test_pause_and_resume_services_require_admin() -> None:
    tree = ast.parse(INIT_PATH.read_text())

    for name in ("_handle_pause", "_handle_resume"):
        handler = _function(tree, name)
        calls = {
            ast.unparse(call.func)
            for call in ast.walk(handler)
            if isinstance(call, ast.Call)
        }
        assert "_async_require_admin" in calls

    guard = _function(tree, "_async_require_admin")
    guard_source = ast.unparse(guard)
    assert "hass.auth.async_get_user" in guard_source
    assert "user is None or not user.is_admin" in guard_source
    assert "raise Unauthorized()" in guard_source


def test_frontend_file_check_runs_in_executor() -> None:
    tree = ast.parse(INIT_PATH.read_text())
    register_frontend = _function(tree, "_async_register_frontend")
    source = ast.unparse(register_frontend)

    assert "await hass.async_add_executor_job(os.path.isfile, card_path)" in source


def test_user_controlled_card_text_is_repaired_then_escaped() -> None:
    source = CARD_PATH.read_text()

    assert "_sanitize(" not in source
    assert "const sharedEsc = (s) => String(s == null ? '' : s)" in source
    assert "window._haToolsEsc" not in source
    assert "String(s == null ? '' : s).replace" in source
    assert "typeof s === 'string' ? s.replace" not in source
    assert "_repairMojibake(str)" in source
    assert '${_esc(this._repairMojibake(cam.name))}' in source
    assert 'aria-label="Camera: ${_esc(this._repairMojibake(cam.name))}"' in source
    assert 'data-camera="${_esc(cam.entity_id)}"' in source
    assert 'value="${_esc(f.label)}"' in source


def test_declared_floor_and_legacy_card_match_shipped_build() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text())

    assert hacs["homeassistant"] == "2024.7.0"
    assert (ROOT / "ha-frigate-privacy.js").read_bytes() == CARD_PATH.read_bytes()


def test_card_does_not_mutate_other_ha_tools_cards() -> None:
    source = CARD_PATH.read_text()

    for global_injector_fragment in (
        "SPLIT_TAGS",
        "deepFindAll",
        "__haToolsSplitDonateInjector",
        "window.addEventListener('hashchange'",
        "window.addEventListener('popstate'",
        "pollCount >= 100",
    ):
        assert global_injector_fragment not in source

    assert "_buildIntroBanner()" in source
    assert "_buildDonateFooter()" in source
    assert 'data-intro="ha-frigate-privacy"' in source
