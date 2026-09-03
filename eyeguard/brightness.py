"""Screen brightness control.

Two code paths are supported:

* **External monitors** use the DDC/CI physical-monitor API (``dxva2.dll``),
  which lets us set each monitor's brightness independently (0..100).
* **The built-in laptop panel** usually exposes no physical-monitor handle, so
  it is driven through the WMI ``WmiMonitorBrightnessMethods`` interface via
  pywin32.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from .mapping import clamp

user32 = ctypes.windll.user32
dxva2 = ctypes.windll.dxva2

MONITORINFOF_PRIMARY = 0x1


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [
        ("hPhysicalMonitor", wintypes.HANDLE),
        ("szPhysicalMonitorDescription", wintypes.WCHAR * 128),
    ]


MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HMONITOR,
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    wintypes.LPARAM,
)

user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC,
    ctypes.c_void_p,
    MonitorEnumProc,
    wintypes.LPARAM,
]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL

dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
    wintypes.HMONITOR,
    ctypes.POINTER(wintypes.DWORD),
]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
    wintypes.HMONITOR,
    wintypes.DWORD,
    ctypes.POINTER(PHYSICAL_MONITOR),
]
dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
dxva2.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.DestroyPhysicalMonitors.restype = wintypes.BOOL
dxva2.GetMonitorBrightness.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
]
dxva2.GetMonitorBrightness.restype = wintypes.BOOL
dxva2.SetMonitorBrightness.argtypes = [wintypes.HANDLE, wintypes.DWORD]
dxva2.SetMonitorBrightness.restype = wintypes.BOOL


@dataclass
class Monitor:
    hmonitor: int
    device: str
    primary: bool
    rect: tuple = (0, 0, 0, 0)
    description: str = ""
    physical_handle: int = 0
    kind: str = "internal"  # "internal" (WMI/software) or "external" (DDC/CI)

    @property
    def name(self) -> str:
        return self.description or self.device


class BrightnessController:
    """Enumerate displays and set/get brightness on all of them."""

    def __init__(self):
        self.monitors: list[Monitor] = []
        self._physical_structs: list = []
        self._wmi_original: int | None = None
        self._external_originals: dict[int, int] = {}
        self.refresh()
        self.capture_originals()

    def refresh(self) -> None:
        self._release_physical()
        self.monitors = []
        self._physical_structs = []
        found: list[tuple[int, str, bool]] = []

        def callback(hmonitor, hdc, lprect, lparam) -> bool:
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                r = info.rcMonitor
                found.append(
                    (
                        hmonitor,
                        info.szDevice,
                        bool(info.dwFlags & MONITORINFOF_PRIMARY),
                        (r.left, r.top, r.right, r.bottom),
                    )
                )
            return True

        cb = MonitorEnumProc(callback)
        user32.EnumDisplayMonitors(None, None, cb, 0)

        for hmonitor, device, primary, rect in found:
            mon = Monitor(hmonitor=int(hmonitor), device=device, primary=primary, rect=rect)
            count = wintypes.DWORD(0)
            if dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
                hmonitor, ctypes.byref(count)
            ) and count.value > 0:
                arr = (PHYSICAL_MONITOR * count.value)()
                if dxva2.GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, arr):
                    # Keep the array alive so the handles stay valid for cleanup.
                    self._physical_structs.append(arr)
                    handle = arr[0].hPhysicalMonitor
                    # Only trust the handle if DDC/CI actually responds. The
                    # internal panel sometimes reports a bogus handle that
                    # fails GetMonitorBrightness; treat those as internal.
                    if handle and self._physical_get(int(handle)) is not None:
                        mon.physical_handle = int(handle)
                        mon.description = arr[0].szPhysicalMonitorDescription
                        mon.kind = "external"
            self.monitors.append(mon)

    def _release_physical(self) -> None:
        for arr in self._physical_structs:
            try:
                dxva2.DestroyPhysicalMonitors(len(arr), arr)
            except Exception:
                pass
        self._physical_structs = []

    def list_monitors(self) -> list[dict]:
        return [
            {
                "name": m.name,
                "device": m.device,
                "kind": m.kind,
                "primary": m.primary,
            }
            for m in self.monitors
        ]

    # ---- WMI (built-in laptop panel) -------------------------------------
    @staticmethod
    def _wmi_set(value: int) -> bool:
        try:
            import win32com.client  # type: ignore
        except Exception:
            return False
        try:
            wmi = win32com.client.GetObject("winmgmts:root/wmi")
            for m in wmi.ExecQuery("SELECT * FROM WmiMonitorBrightnessMethods"):
                m.WmiSetBrightness(1, int(value))
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def _wmi_get():
        try:
            import win32com.client  # type: ignore
        except Exception:
            return None
        try:
            wmi = win32com.client.GetObject("winmgmts:root/wmi")
            for m in wmi.ExecQuery("SELECT * FROM WmiMonitorBrightness"):
                return int(m.CurrentBrightness)
        except Exception:
            return None
        return None

    @staticmethod
    def _physical_get(handle: int) -> int | None:
        mn = wintypes.DWORD(0)
        cur = wintypes.DWORD(0)
        mx = wintypes.DWORD(0)
        if dxva2.GetMonitorBrightness(
            handle, ctypes.byref(mn), ctypes.byref(cur), ctypes.byref(mx)
        ):
            return int(cur.value)
        return None

    def capture_originals(self) -> None:
        """Record each display's brightness so it can be restored on exit."""
        self._wmi_original = self._wmi_get()
        self._external_originals = {}
        for mon in self.monitors:
            if mon.physical_handle:
                cur = self._physical_get(mon.physical_handle)
                if cur is not None:
                    self._external_originals[mon.physical_handle] = cur

    def restore(self) -> None:
        """Restore every display to the brightness captured at startup."""
        if self._wmi_original is not None:
            self._wmi_set(self._wmi_original)
        for handle, value in self._external_originals.items():
            try:
                dxva2.SetMonitorBrightness(handle, value)
            except Exception:
                pass

    # ---- public API ------------------------------------------------------
    def set_all(self, value: float, only: list[str] | None = None) -> int:
        """Set every in-scope monitor to *value* (0..100). Returns applied value."""
        value = int(round(clamp(value, 0, 100)))
        touched_wmi = False
        for mon in self.monitors:
            if only and mon.name not in only and mon.device not in only:
                continue
            if mon.physical_handle:
                try:
                    dxva2.SetMonitorBrightness(mon.physical_handle, value)
                except Exception:
                    pass
            else:
                touched_wmi = True
        if touched_wmi:
            self._wmi_set(value)
        return value

    def set_monitor_ddc(self, monitor: Monitor, value: float) -> bool:
        """Set brightness on a single external (DDC/CI) monitor."""
        if not monitor.physical_handle:
            return False
        try:
            return bool(
                dxva2.SetMonitorBrightness(
                    monitor.physical_handle, int(round(clamp(value, 0, 100)))
                )
            )
        except Exception:
            return False

    def set_wmi(self, value: float) -> bool:
        """Set brightness on the internal panel via WMI."""
        return self._wmi_set(int(round(clamp(value, 0, 100))))

    def get_current(self) -> int | None:
        """Average the reported brightness across monitors, or None.

        Used for status display only; the control loop tracks its own value.
        """
        vals: list[int] = []
        for mon in self.monitors:
            if mon.physical_handle:
                cur = self._physical_get(mon.physical_handle)
                if cur is not None:
                    vals.append(cur)
        wmi_val = self._wmi_get()
        if wmi_val is not None:
            vals.append(wmi_val)
        return int(sum(vals) / len(vals)) if vals else None

    def __del__(self):
        try:
            self._release_physical()
        except Exception:
            pass
