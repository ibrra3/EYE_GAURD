"""Verify per-monitor gamma SET works (dims the internal panel).

Applies a dimmed ramp to the internal display, reads it back, then restores
identity. Requires full display access. Run: python scripts/test_gamma.py
"""

import ctypes
import time
from ctypes import wintypes

from eyeguard.brightness import BrightnessController
from eyeguard.gamma import GammaController
from eyeguard.mapping import combined_ramp, identity_ramp

gdi32 = ctypes.windll.gdi32
gdi32.GetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.GetDeviceGammaRamp.restype = wintypes.BOOL


def read_red_max(controller: GammaController, device: str):
    dc = controller._dc_for(device)
    if not dc:
        return None
    ramp = (ctypes.c_ushort * 768)()
    if not gdi32.GetDeviceGammaRamp(dc, ctypes.byref(ramp)):
        return None
    return ramp[255]


def main() -> None:
    bc = BrightnessController()
    gamma = GammaController()
    internal = next((m for m in bc.monitors if not m.physical_handle), None)
    if internal is None:
        print("No internal panel found; nothing to test.")
        return
    dev = internal.device
    print(f"Internal panel device: {dev}")

    before = read_red_max(gamma, dev)
    print(f"R[255] before: {before}")

    gamma.apply(dev, combined_ramp(40, 0))
    time.sleep(0.5)
    dimmed = read_red_max(gamma, dev)
    print(f"R[255] dimmed (target ~34405): {dimmed}")

    gamma.apply(dev, identity_ramp())
    time.sleep(0.5)
    after = read_red_max(gamma, dev)
    print(f"R[255] restored: {after}")

    if before == 65535 and dimmed is not None and dimmed < 65535 and after == 65535:
        print("GAMMA SET TEST PASSED: the internal panel gamma responds.")
    else:
        print("GAMMA SET TEST INCONCLUSIVE: read-back did not match expectations.")


if __name__ == "__main__":
    main()
