"""Diagnose the display/brightness capabilities of this machine.

Read-only: queries WMI brightness classes and enumerates display devices.
Run:  python scripts/diagnose.py
"""

import ctypes
from ctypes import wintypes


def wmi_probe():
    print("=== WMI (root/wmi) ===")
    try:
        import win32com.client  # type: ignore
    except Exception as exc:
        print("  win32com unavailable:", exc)
        return
    try:
        wmi = win32com.client.GetObject("winmgmts:root/wmi")
    except Exception as exc:
        print("  GetObject failed:", exc)
        return

    for cls in ("WmiMonitorBrightness", "WmiMonitorBrightnessMethods"):
        print(f"  --- {cls} ---")
        try:
            items = wmi.ExecQuery(f"SELECT * FROM {cls}")
            n = 0
            for m in items:
                n += 1
                props = {}
                for p in m.Properties_:
                    try:
                        props[p.Name] = p.Value
                    except Exception:
                        props[p.Name] = "<err>"
                print("   ", props)
            if n == 0:
                print("    (no instances)")
        except Exception as exc:
            print("    query error:", exc)


def display_devices():
    print("=== EnumDisplayDevices ===")
    DISPLAY_DEVICE_ACTIVE = 0x1

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("DeviceName", wintypes.WCHAR * 32),
            ("DeviceString", wintypes.WCHAR * 128),
            ("StateFlags", wintypes.DWORD),
            ("DeviceID", wintypes.WCHAR * 128),
            ("DeviceKey", wintypes.WCHAR * 128),
        ]

    user32 = ctypes.windll.user32
    user32.EnumDisplayDevicesW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(DISPLAY_DEVICEW),
        wintypes.DWORD,
    ]
    user32.EnumDisplayDevicesW.restype = wintypes.BOOL

    i = 0
    while True:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        active = "active" if dd.StateFlags & DISPLAY_DEVICE_ACTIVE else "inactive"
        print(f"  [{i}] {dd.DeviceName}  {dd.DeviceString}  ({active})")
        i += 1


if __name__ == "__main__":
    wmi_probe()
    display_devices()
