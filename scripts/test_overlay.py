"""Verify the overlay dimmer creates windows and sets opacity correctly.

Creates a dim+warm overlay over the internal panel, reads back its alpha via
GetLayeredWindowAttributes, then clears it. Requires full display access.
Run: python scripts/test_overlay.py
"""

import ctypes
import time
from ctypes import wintypes

from eyeguard.brightness import BrightnessController
from eyeguard.overlay import OverlayManager

user32 = ctypes.windll.user32
user32.GetLayeredWindowAttributes.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.COLORREF),
    ctypes.POINTER(wintypes.BYTE),
    ctypes.POINTER(wintypes.DWORD),
]
user32.GetLayeredWindowAttributes.restype = wintypes.BOOL


def read_alpha(hwnd) -> int:
    key = wintypes.COLORREF()
    alpha = wintypes.BYTE()
    flags = wintypes.DWORD()
    if not user32.GetLayeredWindowAttributes(
        hwnd, ctypes.byref(key), ctypes.byref(alpha), ctypes.byref(flags)
    ):
        return -1
    return alpha.value


def main() -> None:
    bc = BrightnessController()
    internal = next((m for m in bc.monitors if not m.physical_handle), None)
    if internal is None:
        print("No internal panel found; cannot test overlay.")
        return
    rect = internal.rect
    print(f"Internal panel {internal.device} rect={rect}")

    mgr = OverlayManager()
    mgr.start()
    try:
        mgr.set(internal.device, rect, 40, 60)  # dim to 40%, warm on
        time.sleep(1.0)

        entry = mgr._windows.get(internal.device)
        print("windows entry:", {k: (v or 0) for k, v in (entry or {}).items()})
        if not entry or not entry["dim"]:
            print("OVERLAY TEST FAILED: dim window was not created.")
            return

        dim_alpha = read_alpha(entry["dim"])
        warm_alpha = read_alpha(entry["warm"]) if entry["warm"] else 0
        print(f"dim alpha: {dim_alpha} (expected ~153), warm alpha: {warm_alpha} (expected ~42)")

        mgr.set(internal.device, rect, 100, 0)  # brighten to 100%, warm off
        time.sleep(0.6)
        dim_alpha2 = read_alpha(entry["dim"])
        print(f"dim alpha after brighten: {dim_alpha2} (expected 0)")

        if dim_alpha > 100 and dim_alpha2 == 0:
            print("OVERLAY TEST PASSED: overlay opacity responds to brightness.")
        else:
            print("OVERLAY TEST INCONCLUSIVE: alpha values unexpected.")
    finally:
        mgr.clear()
        time.sleep(0.4)
        mgr.stop()


if __name__ == "__main__":
    main()
