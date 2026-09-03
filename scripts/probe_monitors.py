"""Per-monitor brightness probe (read-only)."""

import ctypes
from ctypes import wintypes

from eyeguard.brightness import BrightnessController

dxva2 = ctypes.windll.dxva2
dxva2.GetMonitorBrightness.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
]
dxva2.GetMonitorBrightness.restype = wintypes.BOOL


def main() -> None:
    c = BrightnessController()
    print("=== WMI internal panel ===")
    print("  wmi_get():", c._wmi_get())

    print("=== Enumerated monitors ===")
    for m in c.monitors:
        print(
            f"  {m.name!r}  dev={m.device}  kind={m.kind}  "
            f"primary={m.primary}  handle={m.physical_handle}"
        )
        if m.physical_handle:
            mn = wintypes.DWORD()
            cur = wintypes.DWORD()
            mx = wintypes.DWORD()
            ok = dxva2.GetMonitorBrightness(
                m.physical_handle, ctypes.byref(mn), ctypes.byref(cur), ctypes.byref(mx)
            )
            print(f"    DDC/CI: ok={ok} min={mn.value} cur={cur.value} max={mx.value}")


if __name__ == "__main__":
    main()
