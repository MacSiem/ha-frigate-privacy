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
WS_PATH = ROOT / "custom_components/ha_frigate_privacy/websocket_api.py"
BINARY_SENSOR_PATH = (
    ROOT / "custom_components/ha_frigate_privacy/binary_sensor.py"
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


def test_startup_recovery_is_gated_before_external_mutations() -> None:
    tree = ast.parse(INIT_PATH.read_text())
    setup = _function(tree, "async_setup_entry")
    source = ast.unparse(setup)

    not_ready = source.index("bucket[DATA_RECOVERY_READY] = False")
    recovery = source.index("await scheduler.async_tick()")
    websocket_registration = source.index("async_register_commands(hass)")
    service_registration = source.index("_async_register_services(hass)")

    assert not_ready < websocket_registration
    assert recovery < websocket_registration
    assert recovery < service_registration

    for name in ("_handle_pause", "_handle_resume"):
        handler = _function(tree, name)
        assert "_require_recovery_ready(hass)" in ast.unparse(handler)


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
    assert 'data-camera="${_esc(cam.camera_id)}"' in source
    assert 'value="${_esc(form.label)}"' in source


def test_every_websocket_command_is_admin_only() -> None:
    tree = ast.parse(WS_PATH.read_text())
    handlers = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("_ws_")
    ]
    assert handlers
    for handler in handlers:
        decorators = {ast.unparse(item) for item in handler.decorator_list}
        assert "websocket_api.require_admin" in decorators, handler.name


def test_websocket_mutations_use_scheduler_owned_tasks() -> None:
    source = WS_PATH.read_text()

    assert "hass.async_create_task" not in source
    assert source.count("scheduler.async_request_tick()") >= 2


def test_service_path_uses_same_idempotent_manual_coordinator() -> None:
    source = INIT_PATH.read_text()

    assert 'source="service"' not in source
    assert 'source="manual"' in source
    assert source.count('operation_id=call.data.get("operation_id")') == 2


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


def test_automation_sensor_does_not_expose_admin_only_evidence() -> None:
    source = BINARY_SENSOR_PATH.read_text()
    tree = ast.parse(source)
    getter = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "extra_state_attributes"
    )
    getter_source = ast.unparse(getter)

    for private_field in (
        '"camera_id"',
        '"stream_type"',
        '"source"',
        '"reason"',
        '"observed_at"',
        '"schedule_id"',
        '"ends_at"',
        '"operation_id"',
        '"switches"',
        '"skipped"',
        '"target_outcomes"',
    ):
        assert private_field not in getter_source


def test_notifications_and_custom_event_do_not_publish_exact_household_topology() -> None:
    control_source = (ROOT / "custom_components/ha_frigate_privacy/control.py").read_text()
    scheduler_source = (ROOT / "custom_components/ha_frigate_privacy/scheduler.py").read_text()

    assert "Affected entities:" not in control_source
    assert "{detail or 'unknown'}" not in control_source
    assert "', '.join(on_list)" not in scheduler_source
    assert '"camera_id": camera_id' not in scheduler_source
    assert '"source": state.get("source")' not in scheduler_source
    assert '"on_switches": on_list' not in scheduler_source
    assert '"Frigate Privacy pause for %s' not in scheduler_source
    assert '_LOGGER.exception(' not in WS_PATH.read_text()
    assert '"replay_saturated"' in WS_PATH.read_text()
    assert '"replay_integrity"' in WS_PATH.read_text()
    assert '"storage_failed"' in WS_PATH.read_text()

    for private_log_fragment in (
        '"Failed to pause %s',
        '"Failed to stop camera stream %s',
        '"Failed to extend privacy pause for %s',
        '"Fail-safe re-pause failed for %s',
        '"Could not persist fail-safe evidence for %s',
    ):
        assert private_log_fragment not in control_source
