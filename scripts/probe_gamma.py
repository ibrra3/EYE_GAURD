"""Probe per-monitor gamma ramp access (read-only)."""

import ctypes
from ctypes import wintypes

from eyeguard.brightness import MONITORINFOEXW, MonitorEnumProc

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC, ctypes.c_void_p, MonitorEnumProc, wintypes.LPARAM,
]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
gdi32.CreateDCW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
]
gdi32.CreateDCW.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.GetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.GetDeviceGammaRamp.restype = wintypes.BOOL


def main() -> None:
    monitors = []

    def cb(hmonitor, hdc, lprect, lparam) -> bool:
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            monitors.append(info)
        return True

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(cb), 0)

    for info in monitors:
        r = info.rcMonitor
        w, h = r.right - r.left, r.bottom - r.top
        primary = bool(info.dwFlags & 1)
        print(
            f"{info.szDevice}  primary={primary}  "
            f"rect=({r.left},{r.top},{r.right},{r.bottom})  {w}x{h}"
        )

        dc = gdi32.CreateDCW("DISPLAY", info.szDevice, None, None)
        print(f"    CreateDC('DISPLAY', {info.szDevice}) -> {dc}")
        if dc:
            ramp = (ctypes.c_ushort * 768)()
            ok = gdi32.GetDeviceGammaRamp(dc, ctypes.byref(ramp))
            print(
                f"    GetDeviceGammaRamp: ok={ok}  "
                f"R[255]={ramp[255]} G[255]={ramp[255 + 256]} B[255]={ramp[255 + 512]}"
            )
            gdi32.DeleteDC(dc)


if __name__ == "__main__":
    main()
