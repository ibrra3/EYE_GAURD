"""Global hotkeys via Win32 ``RegisterHotKey``.

* ``Ctrl+Alt+E`` — toggle eye protection
* ``Ctrl+Alt+M`` — cycle comfort mode (Morning → Evening → Night → Dark Room)
* ``Ctrl+Alt+B`` — toggle auto-brightness

Hotkeys are registered on a dedicated thread with its own message pump so they
work regardless of which window has focus.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

from .notify import show

MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 1

VK_E = 0x45
VK_M = 0x4D
VK_B = 0x42

user32 = ctypes.windll.user32
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
    wintypes.UINT, wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

MODES = ["morning", "evening", "night", "dark_room"]


class HotkeyManager:
    def __init__(self, config, engine):
        self.config = config
        self.engine = engine
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # id -> (action, vk)
        self._map = {1: ("eye", VK_E), 2: ("mode", VK_M), 3: ("toggle", VK_B)}

    def start(self) -> None:
        if not self.config.data.get("hotkeys", {}).get("enabled", True):
            return
        self._thread = threading.Thread(
            target=self._run, name="eyeguard-hotkeys", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        mods = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
        for hid, (_, vk) in self._map.items():
            user32.RegisterHotKey(None, hid, mods, vk)
        try:
            msg = wintypes.MSG()
            while not self._stop.is_set():
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY:
                        self._handle(msg.wParam)
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.02)
        finally:
            for hid in self._map:
                user32.UnregisterHotKey(None, hid)

    def _handle(self, hid) -> None:
        action = self._map.get(int(hid), ("", 0))[0]
        if action == "eye":
            e = self.config.eye
            e["enabled"] = not bool(e.get("enabled", True))
            self.config.save()
            self.engine.refresh_outputs()
            show("EyeGuard", f"Eye protection {'ON' if e['enabled'] else 'OFF'}")
        elif action == "mode":
            cur = self.config.data.get("mode", "morning")
            nxt = MODES[(MODES.index(cur) + 1) % len(MODES)] if cur in MODES else MODES[0]
            if self.config.apply_mode(nxt):
                self.engine.refresh_outputs()
                show("EyeGuard", f"Mode: {nxt.replace('_', ' ').title()}")
        elif action == "toggle":
            g = self.config.data
            g["enabled"] = not bool(g.get("enabled", True))
            self.config.save()
            self.engine.refresh_outputs()
            show("EyeGuard", f"Auto-brightness {'ON' if g['enabled'] else 'OFF'}")
