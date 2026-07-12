"""Constants for Frigate Privacy."""

from __future__ import annotations

DOMAIN = "ha_frigate_privacy"
VERSION = "5.0.5"

EVENT_STATE_CHANGED = f"{DOMAIN}_state_changed"

DATA_FRONTEND_REGISTERED = "_frontend_registered"
DATA_SCHEDULER = "scheduler"
DATA_SERVICES_REGISTERED = "_services_registered"
DATA_STORAGE = "storage"
DATA_WS_REGISTERED = "_ws_registered"

SERVICE_PAUSE_CAMERA = "pause_camera"
SERVICE_RESUME_CAMERA = "resume_camera"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

STREAM_TYPES = ("all", "main", "sub")
