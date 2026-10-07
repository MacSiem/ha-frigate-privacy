"""Constants for Frigate Privacy."""

from __future__ import annotations

DOMAIN = "ha_frigate_privacy"
VERSION = "6.1.0"
CARD_FILENAME = "ha-frigate-privacy-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
STATIC_URL_BASE = f"/{DOMAIN}"
CARD_ELEMENT = "ha-frigate-privacy"
PANEL_URL_PATH = "ha-frigate-privacy"
PANEL_TITLE = "Frigate Privacy"
PANEL_ICON = "mdi:cctv-off"

EVENT_STATE_CHANGED = f"{DOMAIN}_state_changed"

DATA_FRONTEND_REGISTERED = "_frontend_registered"
DATA_PANEL_REGISTERED = "_panel_registered"
DATA_RECOVERY_READY = "recovery_ready"
DATA_SCHEDULER = "scheduler"
DATA_SERVICES_REGISTERED = "_services_registered"
DATA_STORAGE = "storage"
DATA_WS_REGISTERED = "_ws_registered"

SERVICE_PAUSE_CAMERA = "pause_camera"
SERVICE_RESUME_CAMERA = "resume_camera"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

STREAM_TYPES = ("all", "main", "sub")
