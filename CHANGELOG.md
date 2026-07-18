# Changelog

## 5.0.10 (2026-07-18)

- Docs: correct the stream-type values in the feature table (all / main / sub, not detect/record/all).

## 5.0.9 (2026-07-18)

- Fix (UI): the small accent dot before section titles no longer detaches from the title text (it was pushed to the opposite edge by the header's flex space-between); it is now pinned next to the title.

## 5.0.8 (2026-07-17)

- Fix (UI): responsive tab bar — tabs stretch to fill the card width and wrap on narrow layouts instead of being pinned to content width and clipped (shared HA Tools tab styling).

## 5.0.8 (2026-07-17)

- Fix (UI): responsive tab bar — tabs now stretch to fill the card width and wrap on narrow layouts instead of being pinned to content width and clipped (shared HA Tools tab styling; was `flex:none`+`width:fit-content`).

## 5.0.6 (2026-07-12)

- **Manual-override detection (rock-solid pause state).** When switches that a
  privacy pause turned off are re-enabled outside the integration (Frigate UI,
  HA dashboard, another automation), the pause no longer stays "active" as a
  phantom: manual pauses are cancelled (remaining switches restored, state
  cleared), scheduled windows are marked `overridden` (not re-applied against
  the user's choice). Both fire a `ha_frigate_privacy_pause_interrupted` event
  and create a persistent notification explaining what happened.
- Detection is instant (state listener on the paused switches) with a
  per-minute tick as backstop, and a 90 s grace period so MQTT/Frigate
  confirmation lag is never misread as an override.
- New pure helper `decide_manual_override` in `failsafe.py` + 4 unit tests.

## [5.0.5] - 2026-07-12

- Fix: pause-duration input is now clamped client-side to the server-accepted
  range (1-1440 min, matching `vol.Range` in `websocket_api.py`); out-of-range
  or non-numeric values are corrected and a clear error toast (EN/PL) is shown
  instead of a silent server rejection.
- Chore: aligned card JS version header with `manifest.json`/`const.py` (5.0.5).

## [5.0.4] - 2026-07-12

- Fix: the card now renders for non-admin Home Assistant users — read-only websocket
  commands (`list_cameras`, `get_schedules`, `get_state`) no longer require admin.
  Mutating commands (`set_schedule`, `pause_camera`, `resume_camera`) stay admin-only
  on purpose: disabling camera recording/detection is a privileged, security-relevant
  action, so non-admins get a view-only card.
- Chore: aligned `const.VERSION` (was stale at 5.0.1) with `manifest.json` (5.0.4).

## [5.0.3] - 2026-06-15

- Theme: dark/light now follows the active Home Assistant theme (luminance of --card-background-color) instead of OS prefers-color-scheme.


## [5.0.2] - 2026-06-15

- Theme: dark/light now follows the active Home Assistant theme (luminance of --card-background-color) instead of OS prefers-color-scheme.

## [5.0.1] - 2026-06-13

### Added
- getGridOptions() for correct sizing in HA sections (grid) layout.

## v5.0.0 — 2026-06-12

### Changed

- Migrated from a Lovelace-card-only HACS plugin to a full Home Assistant integration with a bundled card.
- Added config flow, WebSocket API, server-side schedule/paused-state storage, services, scheduler, and binary sensors.
- Added privacy-first fail-safe resume handling: failed or uncertain resume keeps cameras marked paused and creates a persistent notification.
- The bundled card migrates existing browser-local schedules to integration storage on first successful WebSocket connection, while the root card remains usable in legacy localStorage mode.

## v4.1.7 — 2026-05-18

### Fixed

- **Pause re-entrancy + immediate user feedback.** The Quick Pause / Custom Pause flow could feel unresponsive on first click — the first `_ensureHAHelpers()` call on a fresh session issues a `config/automation/config` WS update to register the auto-resume automation, which can take ~1-2s on a busy HA. While that promise was in flight nothing visible happened, so users hit the button again. Now: a `_pauseInFlight` guard short-circuits re-entrant clicks, and a toast (`⏳ Pausing…`) fires synchronously the moment the button is clicked.
- **Full privacy now stops live camera streaming.** The `All` pause mode turns off the selected `camera.*` entity after disabling Frigate feature switches, and resume turns the camera entity back on before restoring switches. Timer-expiry and schedule automations include the same hard-stop/hard-resume behavior so it works without an open browser.

## v4.1.6 — 2026-05-18

### Added

- **Per-stream privacy mode.** New `What to pause` selector lets you choose which switches go off when you hit Quick pause:
  - **All** — full Frigate pipeline offline (every available switch). Previous v4.1.5 behaviour.
  - **Recording only (main)** — turns off `_recordings` + `_snapshots`; `_detect` / `_motion` / `_audio` keep running so motion / object detection still fire while no video is saved.
  - **Detection only (sub)** — turns off `_detect` / `_motion` / `_audio_detection` (or `_audio` on Frigate 0.14-0.16); recording the current stream continues passively.
- Stream type is persisted to `localStorage` and stored in the active privacy session, so resume restores exactly the subset that was paused (it no longer flips ON switches the user had intentionally left disabled).
- Timer-expiry auto-resume automation is rebuilt with the same stream-type filter, so server-side restore matches the pause.

### Notes

- Schedule windows (Schedule tab) keep the previous behaviour and still pause everything. Stream type for schedules is a follow-up enhancement.

## v4.1.5 — 2026-05-18

### Fixed

- **HACS reviewer concern.** Moved `_ensureHAHelpers()` (timer + input_text + resume-automation) out of the render loop and into the first user-initiated pause/schedule save. The render path is now stateless; HA-native helpers appear only when the user actually exercises a privacy action.

# Changelog — Frigate Privacy

## [4.1.3] - 2026-05-12

### Fixed
- Removed Google Fonts CDN @import (1 occurrence(s)); now uses system font stack with Inter as the preferred locally-installed face.
- Normalized bare `font-family: "Inter", sans-serif` declarations to a complete cross-platform system stack.
- Privacy section in README: claim now matches behaviour (no CDN dependencies).

All notable changes to **Frigate Privacy** are documented here.

## [4.0.0] - 2026-05-10

### Major
- **Split from `MacSiem/ha-tools` monorepo** into a dedicated standalone HACS plugin.
- Bundled Bento Design System CSS inline — no shared dependency required.
- Inlined `_haToolsEsc` XSS sanitizer.
- Persistence keys migrated to per-tool namespace `ha-frigate-privacy-…` (clean break — old data under `ha-tools-…` is **not** migrated automatically).
- Donation/support footer added to the panel.
- Cross-tool discovery banner removed; each tool stands on its own.

### Compatibility

- Home Assistant ≥ 2024.1.0
