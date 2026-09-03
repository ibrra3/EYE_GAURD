"""Screen / foreground-window luminance sampling via GDI.

The active window's rectangle (or the full virtual screen) is captured with
``StretchBlt`` into a small (64x36) bitmap, then averaged into a single
0..255 luminance value using standard Rec. 709 weights.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from .windowinfo import foreground_window_rect

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SRCCOPY = 0x00CC0020
HALFTONE = 4
BI_RGB = 0
DIB_RGB_COLORS = 0

user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetStretchBltMode.restype = ctypes.c_int
gdi32.StretchBlt.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
]
gdi32.StretchBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


class LumaSampler:
    """Sample average screen luminance quickly and cheaply."""

    def __init__(self, sample_w: int = 64, sample_h: int = 36):
        self.sample_w = sample_w
        self.sample_h = sample_h

    def sample(self, mode: str = "foreground"):
        """Return average luminance (0..255), or None on failure."""
        screen_dc = user32.GetDC(None)
        if not screen_dc:
            return None
        try:
            vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
            if mode == "foreground":
                rect = foreground_window_rect()
                if not rect:
                    rect = (vx, vy, vx + vw, vy + vh)
                left, top, right, bottom = rect
            else:
                left, top, right, bottom = vx, vy, vx + vw, vy + vh

            if right <= left or bottom <= top:
                return None
            return self._average(screen_dc, left, top, right, bottom)
        finally:
            user32.ReleaseDC(None, screen_dc)

    def _average(self, screen_dc, left, top, right, bottom):
        sw, sh = self.sample_w, self.sample_h
        src_w = max(1, right - left)
        src_h = max(1, bottom - top)

        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not mem_dc:
            return None
        bmp = gdi32.CreateCompatibleBitmap(screen_dc, sw, sh)
        if not bmp:
            gdi32.DeleteDC(mem_dc)
            return None
        old = gdi32.SelectObject(mem_dc, bmp)
        try:
            gdi32.SetStretchBltMode(mem_dc, HALFTONE)
            if not gdi32.StretchBlt(
                mem_dc, 0, 0, sw, sh, screen_dc, left, top, src_w, src_h, SRCCOPY
            ):
                return None

            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = sw
            bmi.bmiHeader.biHeight = -sh  # top-down DIB
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB

            buf = (ctypes.c_ubyte * (sw * sh * 4))()
            n = gdi32.GetDIBits(mem_dc, bmp, 0, sh, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
            if n <= 0:
                return None
            return self._avg_luma(bytes(buf))
        finally:
            gdi32.SelectObject(mem_dc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem_dc)

    @staticmethod
    def _avg_luma(data: bytes) -> float:
        total = 0.0
        count = 0
        # 32bpp BGRA
        for i in range(0, len(data) - 3, 4):
            b = data[i]
            g = data[i + 1]
            r = data[i + 2]
            total += 0.0722 * b + 0.7152 * g + 0.2126 * r
            count += 1
        return total / count if count else 0.0
