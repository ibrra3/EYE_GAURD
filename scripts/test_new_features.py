"""Smoke-test the newer features (non-destructive)."""
import time

from eyeguard.ambient import AmbientLightSensor
from eyeguard.config import Config
from eyeguard.engine import Engine
from eyeguard.hotkeys import HotkeyManager
from eyeguard.idle import idle_seconds

c = Config()
c.data["schedule"] = {
    "enabled": True,
    "entries": [
        {"time": "00:00", "mode": "night"},
        {"time": "07:00", "mode": "morning"},
        {"time": "19:00", "mode": "night"},
        {"time": "23:00", "mode": "dark_room"},
    ],
}

e = Engine(c)
print("scheduled mode now:", e._scheduled_mode())
assert e._scheduled_mode() in ("morning", "evening", "night", "dark_room")

h = HotkeyManager(c, e)
h.start()
time.sleep(0.5)
print("hotkeys running:", h._thread is not None and h._thread.is_alive())
h.stop()

a = AmbientLightSensor(refresh_seconds=30)
print("ambient lux:", a._read())

print("idle_seconds:", idle_seconds())

e.stop()
print("new-features smoke test done")
