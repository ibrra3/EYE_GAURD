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
