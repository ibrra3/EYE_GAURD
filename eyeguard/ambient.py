"""Ambient light sensor support (best-effort, optional).

Reads the Windows ambient-light sensor through the WinRT ``LightSensor`` API via
a PowerShell one-liner, cached in a background thread. If no sensor is present
(or the call fails), ``get_lux`` returns ``None`` and the engine falls back to
screen luminance only.
"""

from __future__ import annotations

import subprocess
import threading

from .mapping import clamp

CREATE_NO_WINDOW = 0x08000000

_PS_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "[Windows.Devices.Sensors.LightSensor,Windows.Devices.Sensors,"
    "ContentType=WindowsRuntime]|Out-Null;"
    "$s=[Windows.Devices.Sensors.LightSensor]::GetDefault();"
    "if($s){$s.GetCurrentReading().IlluminanceInLux}"
)


class AmbientLightSensor:
    def __init__(self, refresh_seconds: int = 30):
        self._lux = None
        self._refresh = max(10, int(refresh_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="eyeguard-ambient", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def get_lux(self):
        return self._lux

    def _run(self) -> None:
        while not self._stop.is_set():
            self._lux = self._read()
            self._stop.wait(self._refresh)

    def _read(self):
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", _PS_SCRIPT],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=CREATE_NO_WINDOW,
            )
            txt = (out.stdout or "").strip()
            if txt:
                return float(txt)
        except Exception:
            pass
        return None


def lux_to_luma(lux, max_lux: float = 1000.0) -> float:
    """Map an illuminance value (lux) to a 0..255 luminance."""
    return clamp(lux, 0.0, max_lux) / max_lux * 255.0
