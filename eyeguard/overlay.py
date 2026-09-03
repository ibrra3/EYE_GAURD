"""Translucent overlay windows for software dimming + warm tint.

Windows applies a hardware gamma ramp only to the *primary* display, so a
non-primary laptop panel cannot be dimmed that way. This module instead shows
topmost, click-through layered windows (black for dimming, warm orange for the
blue-light tint) over a display, which works on any monitor.

The windows live on a dedicated thread with a small Win32 message pump.
"""

from __future__ import annotations

import ctypes
import queue
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# window styles / flags
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
LWA_ALPHA = 0x2
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SW_SHOWNOACTIVATE = 4
PM_REMOVE = 1
BLACK_BRUSH = 4

# warm orange tint (blue-light filter approximation)
WARM_RGB = (255, 150, 50)


def _colorref(rgb) -> int:
    r, g, b = rgb
    return (b << 16) | (g << 8) | r


def brightness_to_alpha(brightness: float) -> int:
    """Map brightness 0..100 to overlay opacity 0..255 (100 -> transparent)."""
    b = max(0.0, min(100.0, float(brightness)))
    return int(round((100.0 - b) * 2.55))


def warmth_to_alpha(warmth: int) -> int:
    """Map warmth 0..100 to a subtle warm-tint opacity 0..70."""
    w = max(0, min(100, int(warmth)))
    return int(round(w * 0.7))


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p
)


def _setup_signatures() -> None:
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p,
    ]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.UnregisterClassW.restype = wintypes.BOOL

    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND

    user32.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD,
    ]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL

    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL

    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL

    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
        wintypes.UINT, wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t

    gdi32.GetStockObject.argtypes = [ctypes.c_int]
    gdi32.GetStockObject.restype = wintypes.HGDIOBJ
    gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL


class OverlayManager:
    """Manage one dim + one warm overlay window per display."""

    DIM_CLASS = "EyeGuardOverlayDim"
    WARM_CLASS = "EyeGuardOverlayWarm"

    def __init__(self):
        _setup_signatures()
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._windows: dict[str, dict] = {}  # key -> {"dim": hwnd, "warm": hwnd}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._wndproc = None
        self._warm_brush = None

    # ---- lifecycle (called from the engine thread) -----------------------
    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="eyeguard-overlay", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def set(self, key: str, rect, brightness: float, warmth: int) -> None:
        self._q.put(("set", key, tuple(rect), float(brightness), int(warmth)))

    def clear(self) -> None:
        self._q.put(("clear",))

    # ---- manager thread --------------------------------------------------
    def _run(self) -> None:
        self._wndproc = WNDPROC(user32.DefWindowProcW)
        self._warm_brush = gdi32.CreateSolidBrush(_colorref(WARM_RGB))
        self._register_class(self.DIM_CLASS, gdi32.GetStockObject(BLACK_BRUSH))
        self._register_class(self.WARM_CLASS, self._warm_brush)
        try:
            while not self._stop.is_set():
                self._pump()
                self._drain()
                time.sleep(0.02)
        finally:
            for entry in self._windows.values():
                for hwnd in entry.values():
                    if hwnd:
                        user32.DestroyWindow(hwnd)
            self._windows.clear()
            if self._warm_brush:
                gdi32.DeleteObject(self._warm_brush)
            self._unregister_class(self.DIM_CLASS)
            self._unregister_class(self.WARM_CLASS)

    def _pump(self) -> None:
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _drain(self) -> None:
        try:
            while True:
                self._handle(self._q.get_nowait())
        except queue.Empty:
            pass

    def _handle(self, cmd) -> None:
        if cmd[0] == "clear":
            for entry in self._windows.values():
                for hwnd in entry.values():
                    if hwnd:
                        user32.DestroyWindow(hwnd)
            self._windows.clear()
            return
        if cmd[0] != "set":
            return
        _, key, rect, brightness, warmth = cmd
        entry = self._windows.get(key)
        if entry is None:
            entry = {"dim": self._create(self.DIM_CLASS, rect), "warm": None}
            self._windows[key] = entry
        else:
            # Re-cover the display in case its geometry changed.
            self._position(entry["dim"], rect)
            if entry["warm"]:
                self._position(entry["warm"], rect)

        dim_alpha = brightness_to_alpha(brightness)
        warm_alpha = warmth_to_alpha(warmth)

        self._ensure_warm(entry, rect, warm_alpha > 0)
        self._set_alpha(entry["dim"], dim_alpha)
        if entry["warm"]:
            self._set_alpha(entry["warm"], warm_alpha)

    def _ensure_warm(self, entry, rect, want: bool) -> None:
        if want and not entry["warm"]:
            entry["warm"] = self._create(self.WARM_CLASS, rect)
        elif not want and entry["warm"]:
            user32.DestroyWindow(entry["warm"])
            entry["warm"] = None

    def _create(self, class_name: str, rect):
        left, top, right, bottom = rect
        w = max(1, right - left)
        h = max(1, bottom - top)
        exstyle = (
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
            | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )
        hwnd = user32.CreateWindowExW(
            exstyle, class_name, "", WS_POPUP,
            left, top, w, h, None, None, kernel32.GetModuleHandleW(None), None,
        )
        if hwnd:
            user32.SetLayeredWindowAttributes(hwnd, 0, 0, LWA_ALPHA)
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            self._position(hwnd, rect)
        return hwnd

    @staticmethod
    def _position(hwnd, rect) -> None:
        left, top, right, bottom = rect
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, left, top,
            max(1, right - left), max(1, bottom - top),
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    @staticmethod
    def _set_alpha(hwnd, alpha: int) -> None:
        if hwnd:
            user32.SetLayeredWindowAttributes(hwnd, 0, alpha & 0xFF, LWA_ALPHA)

    def _register_class(self, name: str, brush) -> None:
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hIcon = 0
        wc.hCursor = 0
        wc.hbrBackground = brush
        wc.lpszMenuName = None
        wc.lpszClassName = name
        user32.RegisterClassW(ctypes.byref(wc))

    def _unregister_class(self, name: str) -> None:
        user32.UnregisterClassW(name, kernel32.GetModuleHandleW(None))
