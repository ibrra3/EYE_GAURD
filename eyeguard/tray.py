"""System tray icon and menu for EyeGuard."""

from __future__ import annotations

import threading

from .icon import build_icon


class TrayIcon:
    def __init__(self, config, engine, window):
        self.config = config
        self.engine = engine
        self.window = window
        self._icon = None
        self._thread = None

    def start(self) -> None:
        import pystray

        self._icon = pystray.Icon(
            "eyeguard", build_icon(64), "EyeGuard", self._menu()
        )
        self._thread = threading.Thread(
            target=self._icon.run, name="eyeguard-tray", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def _menu(self):
        import pystray

        return pystray.Menu(
            pystray.MenuItem("Open Settings", self._open_settings, default=True),
            pystray.MenuItem("Test laptop dim", self._quick_test),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Auto-adjust brightness",
                self._toggle_enabled,
                checked=lambda item: bool(self.config.data.get("enabled", True)),
            ),
            pystray.MenuItem(
                "Eye protection",
                self._toggle_eye,
                checked=lambda item: bool(self.config.eye.get("enabled", True)),
            ),
            pystray.MenuItem(
                "Pause during videos",
                self._toggle_video,
                checked=lambda item: bool(self.config.video_pause.get("enabled", True)),
            ),
            pystray.MenuItem("Resume auto", self._resume_auto),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    # ---- callbacks (run on the icon thread) ------------------------------
    def _open_settings(self, icon, item):
        self.window.request_show()

    def _quick_test(self, icon, item):
        self.engine.quick_test()

    def _toggle_enabled(self, icon, item):
        self.config.data["enabled"] = not bool(self.config.data.get("enabled", True))
        self.config.save()

    def _toggle_eye(self, icon, item):
        self.config.eye["enabled"] = not bool(self.config.eye.get("enabled", True))
        self.config.save()

    def _toggle_video(self, icon, item):
        self.config.video_pause["enabled"] = not bool(
            self.config.video_pause.get("enabled", True)
        )
        self.config.save()

    def _resume_auto(self, icon, item):
        self.engine.resume_auto()

    def _quit(self, icon, item):
        self.engine.stop()
        self.window.request_quit()
        if self._icon:
            self._icon.stop()
