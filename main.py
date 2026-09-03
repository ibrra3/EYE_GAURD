"""EyeGuard entry point.

Usage:
    python main.py
"""

from eyeguard.config import Config
from eyeguard.engine import Engine
from eyeguard.settings_window import SettingsWindow
from eyeguard.tray import TrayIcon


def main() -> None:
    config = Config()
    engine = Engine(config)
    engine.start()

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
        engine.stop()
        config.save()


if __name__ == "__main__":
    main()
