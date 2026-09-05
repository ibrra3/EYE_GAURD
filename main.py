"""EyeGuard entry point.

Usage:
    python main.py            # starts hidden in the system tray
    python main.py --hidden   # same, explicit no-window start
"""

import sys

from eyeguard.config import Config
from eyeguard.engine import Engine
from eyeguard.hotkeys import HotkeyManager
from eyeguard.settings_window import SettingsWindow
from eyeguard.tray import TrayIcon


def main() -> None:
    # "--hidden" is accepted for clarity; the app always starts in the tray.
    _ = "--hidden" in sys.argv

    config = Config()
    engine = Engine(config)
    engine.start()

    hotkeys = HotkeyManager(config, engine)
    hotkeys.start()

    window = SettingsWindow(config, engine)

    tray = None
    try:
        tray = TrayIcon(config, engine, window)
        tray.start()
    except Exception as exc:  # e.g. pystray/Pillow not installed
        print(f"Warning: system tray unavailable ({exc}). "
              "Use the settings window instead.")

    try:
        window.run()
    finally:
        if tray is not None:
            tray.stop()
        hotkeys.stop()
        engine.stop()
        config.save()


if __name__ == "__main__":
    main()
