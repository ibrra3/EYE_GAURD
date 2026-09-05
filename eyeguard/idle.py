"""User idle detection via Win32 ``GetLastInputInfo``."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.GetLastInputInfo.restype = wintypes.BOOL
kernel32.GetTickCount.argtypes = []
kernel32.GetTickCount.restype = wintypes.DWORD


def idle_seconds() -> int:
    """Return the number of seconds since the last user input (0 on failure)."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0
    ticks = kernel32.GetTickCount()
    diff = (ticks - lii.dwTime) & 0xFFFFFFFF  # handles GetTickCount wraparound
    return int(diff // 1000)
