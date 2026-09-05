"""Tiny cross-module notification helper.

The tray icon registers a callback; the engine and hotkeys call ``show`` to
surface a subtle notification on state changes (mode switch, video pause, etc.).
"""

from __future__ import annotations

_callback = None


def set_callback(cb) -> None:
    global _callback
    _callback = cb


def show(title: str, message: str) -> None:
    if _callback:
        try:
            _callback(title, message)
        except Exception:
            pass
