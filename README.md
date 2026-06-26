# Frigate Privacy

![Preview](banner.png)

Pause and resume Frigate camera privacy switches from Home Assistant, with server-side schedules and fail-safe resume handling.

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg?logo=homeassistant)](https://www.home-assistant.io/) [![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Version](https://img.shields.io/badge/Version-5.0.3-success.svg)](#changelog)

## Screenshots

![Screenshot](screenshot.png)

## Installation

Until this repository is available in the default HACS store:

1. Open HACS -> Integrations -> three-dot menu -> Custom repositories.
2. Add `https://github.com/MacSiem/ha-frigate-privacy` with category **Integration**.
3. Install **Frigate Privacy**.
4. Restart Home Assistant.
5. Go to Settings -> Devices & services -> Add integration -> **Frigate Privacy**.

The integration registers the bundled Lovelace card automatically. Add it to a dashboard with:

```yaml
type: custom:ha-frigate-privacy
```

The legacy root `ha-frigate-privacy.js` file remains available for manual Lovelace resource installs. In that mode the card keeps using browser-local storage and shows a hint to install the integration for server-side schedules.

## What It Adds

- A Home Assistant integration under `custom_components/ha_frigate_privacy`.
- A bundled Lovelace card served from `/ha_frigate_privacy/ha-frigate-privacy-card.js?v=5.0.0`.
- Server-side storage for schedules and paused-camera state.
- WebSocket APIs used by the bundled card.
- Services for automations.
- Binary sensors for active privacy state.

## Services

### `ha_frigate_privacy.pause_camera`

Pauses one camera, a list of cameras, or all discovered Frigate cameras when no camera is provided.

Fields:

- `camera` or `camera_entity_id`: camera entity ID or Frigate camera ID, for example `camera.front_door`.
- `duration_minutes`: optional duration before the server tries to resume.
- `stream_type`: `all`, `main`, or `sub`.

### `ha_frigate_privacy.resume_camera`

Resumes one camera, a list of cameras, or all paused cameras when no camera is provided.

Fields:

- `camera` or `camera_entity_id`: camera entity ID or Frigate camera ID.

## Binary Sensors

For discovered/configured Frigate cameras, the integration creates:

```text
binary_sensor.<camera_id>_privacy_active
```

The sensor is on while that camera remains privacy-paused. Attributes include stream type, source, schedule ID, skipped switches, and resume-blocked state.

## Frigate Compatibility

Camera discovery uses Frigate switch entities such as:

- `switch.<camera>_detect`
- `switch.<camera>_recordings`

Pause/resume supports the pre-0.17 and 0.17+ switch surfaces. Missing optional switches are skipped and reported in WebSocket/service results instead of failing the whole camera operation.

## Fail-Safe Behaviour

Privacy-first resume is explicit in the integration code:

- Before exiting a privacy window, the integration checks that every switch it paused still exists and is available.
- If a switch is missing/unavailable, auto-resume is blocked before toggling anything.
- If a resume service call fails after any switch was turned on, the integration attempts to turn it back off.
- The camera remains marked paused in storage.
- A persistent notification is created with the affected entities.

This prevents the integration from silently clearing privacy state when the actual camera state is uncertain.

## Migrating From v4 Lovelace Card

The bundled v5 card migrates existing browser-local schedules once, on first successful WebSocket connection to the integration. It pushes existing `ha-frigate-privacy-schedules` entries to server storage through `ha_frigate_privacy/set_schedule`, then sets a local migration flag.

If the integration is not installed or not configured, the card continues in legacy mode with browser-local schedules.

## Privacy

- No telemetry, analytics, or tracking.
- No external network calls or CDN assets.
- State is stored locally in Home Assistant via the integration store, or in browser `localStorage` only when using the standalone legacy card.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Support

If this tool makes your Home Assistant life easier, consider supporting development:

- [Buy Me a Coffee](https://buymeacoffee.com/macsiem)
- [PayPal](https://www.paypal.com/donate/?hosted_button_id=Y967H4PLRBN8W)

## License

MIT - see [LICENSE](LICENSE).
