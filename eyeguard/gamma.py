"""Per-monitor gamma ramp control.

Applies a gamma lookup table to a *specific* display by creating a DC for that
monitor's device name (``CreateDC("DISPLAY", device)``) and calling
``SetDeviceGammaRamp``. This powers both the warm blue-light filter and the
software brightness fallback for the internal laptop panel.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from .mapping import identity_ramp

gdi32 = ctypes.windll.gdi32

gdi32.CreateDCW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
]
gdi32.CreateDCW.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.SetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.SetDeviceGammaRamp.restype = wintypes.BOOL


class GammaController:
    """Cache a DC per display and apply/clear gamma ramps on it."""

    def __init__(self):
        self._dcs: dict[str, int] = {}
        self._last: dict[str, tuple] = {}

    def _dc_for(self, device: str):
        dc = self._dcs.get(device)
        if not dc:
            dc = gdi32.CreateDCW("DISPLAY", device, None, None)
            if dc:
                self._dcs[device] = dc
        return dc

    def apply(self, device: str, ramp: list[int]) -> bool:
        """Apply *ramp* (768 words) to *device*, skipping no-op repeats."""
        if not device:
            return False
        key = tuple(ramp)
        if self._last.get(device) == key:
            return True
        dc = self._dc_for(device)
        if not dc:
            return False
        words = (ctypes.c_ushort * len(ramp))(*ramp)
        ok = bool(gdi32.SetDeviceGammaRamp(dc, ctypes.cast(words, ctypes.c_void_p)))
        if ok:
            self._last[device] = key
        return ok

    def clear(self, device: str) -> bool:
        return self.apply(device, identity_ramp())

    def clear_all(self, devices) -> None:
        for device in devices:
            self.clear(device)

    def __del__(self):
        for dc in self._dcs.values():
            try:
                gdi32.DeleteDC(dc)
            except Exception:
                pass
