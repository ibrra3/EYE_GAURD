"""Configuration loading, defaults, and persistence for EyeGuard.

The config lives as JSON under ``%APPDATA%\\EyeGuard\\config.json``. A previous
BrightFlow config (older name) is migrated automatically on first run.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "EyeGuard"
CONFIG_PATH = APP_DIR / "config.json"
LEGACY_CONFIG_PATH = (
    Path(os.environ.get("APPDATA", str(Path.home()))) / "BrightFlow" / "config.json"
)


DEFAULTS: dict = {
    "version": 1,
    "enabled": True,               # master auto-adjust switch
    "interval_seconds": 1.5,       # how often to poll the active app + content
    "luma_sample_mode": "foreground",  # "foreground" or "fullscreen"
    "link_displays": True,         # True = all displays share one profile
    "per_monitor": {},             # {device: {"brightness": {...}, "eye_protection": {...}, "mode": "..."}}
    "hotkeys": {"enabled": True},  # Ctrl+Alt+E (eye) / M (mode) / B (brightness)
    "idle": {"enabled": False, "minutes": 10, "dim_to": 25},
    "ambient_light": {
        "enabled": False,          # blend the light sensor with screen content
        "weight": 0.5,             # 0..1; how much ambient light influences
        "refresh_seconds": 30,
        "max_lux": 1000,           # lux mapped to "full brightness"
    },
    "schedule": {
        "enabled": False,
        "entries": [],             # [{"time": "19:00", "mode": "night"}, ...]
    },
    "mode": "morning",             # active comfort profile (shared)
    "modes": {
        "morning": {
            "label": "Morning",
            "description": "Natural daylight — subtle tint, full brightness range.",
            "brightness": {"dark_target": 85, "bright_target": 40, "min": 10, "max": 100},
            "eye_protection": {"always_on": False, "warmth": 40, "dim_percent": 10},
        },
        "evening": {
            "label": "Evening",
            "description": "Softer and warmer — reduced blue light and brightness.",
            "brightness": {"dark_target": 75, "bright_target": 35, "min": 10, "max": 90},
            "eye_protection": {"always_on": False, "warmth": 60, "dim_percent": 15},
        },
        "night": {
            "label": "Night",
            "description": "Strong warm filter, dimmer, eye protection always on.",
            "brightness": {"dark_target": 60, "bright_target": 25, "min": 8, "max": 70},
            "eye_protection": {"always_on": True, "warmth": 80, "dim_percent": 25},
        },
        "dark_room": {
            "label": "Dark Room",
            "description": "Maximum comfort in the dark — very dim and warm.",
            "brightness": {"dark_target": 40, "bright_target": 15, "min": 5, "max": 50},
            "eye_protection": {"always_on": True, "warmth": 100, "dim_percent": 35},
        },
    },
    "brightness": {
        "dark_target": 85,         # brightness when content is dark
        "bright_target": 40,       # brightness when content is bright/white
        "min": 10,                 # floor for automatic adjustment
        "max": 100,                # ceiling for automatic adjustment
        "max_step_per_sec": 60,    # transition speed (% per second)
        "use_software_for_internal": True,  # overlay dim for the laptop panel
    },
    "eye_protection": {
        "enabled": True,
        "always_on": False,        # force warm filter regardless of content
        "auto_trigger_white": True,  # trigger on white/paper content
        "white_luma_threshold": 200,
        "warmth": 60,              # 0..100; higher = warmer / less blue
        "dim_percent": 15,         # extra brightness reduction while active
    },
    "video_pause": {
        "enabled": True,           # hold brightness while watching a video
        "match": (
            r"youtube|netflix|twitch|vimeo|prime ?video|disney\+|hulu|"
            r"crunchyroll|dailymotion|vlc|mpv|potplayer|plex|"
            r"\.mp4|\.mkv|\.avi|\.webm"
        ),
    },
    "monitors": [],                # monitor names to control; empty = all
    "app_rules": [
        {
            "name": "Example: code editor",
            "match": r"code\.exe|devenv|pycharm|visual studio",
            "enabled": True,
            "brightness": "auto",  # "auto" or a fixed number 0..100
            "eye_protection": None,  # None = use global; True/False = force
        },
    ],
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* onto a copy of *base*."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Thin wrapper around the JSON settings document."""

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.data = copy.deepcopy(DEFAULTS)
        self._migrate()
        self.load()

    def _migrate(self) -> None:
        if not self.path.exists() and LEGACY_CONFIG_PATH.exists():
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(LEGACY_CONFIG_PATH, self.path)
            except OSError:
                pass

    def load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data = _deep_merge(DEFAULTS, raw)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    @property
    def brightness(self) -> dict:
        return self.data["brightness"]

    @property
    def eye(self) -> dict:
        return self.data["eye_protection"]

    @property
    def video_pause(self) -> dict:
        return self.data["video_pause"]

    @property
    def rules(self) -> list:
        return self.data["app_rules"]

    @property
    def modes(self) -> dict:
        return self.data["modes"]

    @property
    def link_displays(self) -> bool:
        return bool(self.data.get("link_displays", True))

    def set_link_displays(self, linked: bool) -> None:
        self.data["link_displays"] = bool(linked)
        self.save()

    def _override(self, device: str) -> dict:
        """Return (creating if needed) the per-monitor override for *device*."""
        pm = self.data.setdefault("per_monitor", {})
        return pm.setdefault(device, {})

    def brightness_for(self, device: str | None) -> dict:
        """Effective brightness settings for a monitor (shared + override)."""
        base = self.brightness
        if device is None or self.link_displays:
            return base
        ov = self.data.get("per_monitor", {}).get(device, {})
        if not ov.get("brightness"):
            return base
        merged = dict(base)
        merged.update(ov["brightness"])
        return merged

    def eye_for(self, device: str | None) -> dict:
        """Effective eye-protection settings for a monitor."""
        base = self.eye
        if device is None or self.link_displays:
            return base
        ov = self.data.get("per_monitor", {}).get(device, {})
        if not ov.get("eye_protection"):
            return base
        merged = dict(base)
        merged.update(ov["eye_protection"])
        return merged

    def mode_for(self, device: str | None) -> str:
        if device is not None and not self.link_displays:
            ov = self.data.get("per_monitor", {}).get(device, {})
            if ov.get("mode"):
                return ov["mode"]
        return self.data.get("mode", "morning")

    def set_brightness_values(self, values: dict, device: str | None = None) -> None:
        if device is None:
            self.brightness.update(values)
        else:
            self._override(device).setdefault("brightness", {}).update(values)
        self.save()

    def set_eye_values(self, values: dict, device: str | None = None) -> None:
        if device is None:
            self.eye.update(values)
        else:
            self._override(device).setdefault("eye_protection", {}).update(values)
        self.save()

    def apply_mode(self, name: str, device: str | None = None) -> bool:
        """Apply a comfort profile to the shared profile or a single display."""
        preset = self.data.get("modes", {}).get(name)
        if not preset:
            return False
        if device is None:
            self.brightness.update(preset.get("brightness", {}))
            self.eye.update(preset.get("eye_protection", {}))
            self.data["mode"] = name
        else:
            ov = self._override(device)
            ov.setdefault("brightness", {}).update(preset.get("brightness", {}))
            ov.setdefault("eye_protection", {}).update(preset.get("eye_protection", {}))
            ov["mode"] = name
        self.save()
        return True
