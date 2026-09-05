"""Full-wiring smoke test: start every component, wait, then stop cleanly."""
import time

from eyeguard.config import Config
from eyeguard.engine import Engine
from eyeguard.hotkeys import HotkeyManager
from eyeguard.settings_window import SettingsWindow
from eyeguard.tray import TrayIcon

c = Config()
e = Engine(c)
e.start()
h = HotkeyManager(c, e)
h.start()
w = SettingsWindow(c, e)
t = TrayIcon(c, e, w)
t.start()

time.sleep(3)

t.stop()
h.stop()
e.stop()
w.root.destroy()
print("full app start/stop OK")
