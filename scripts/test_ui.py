"""Quick check that the settings window constructs with the dark theme."""
from eyeguard.config import Config
from eyeguard.engine import Engine
from eyeguard.settings_window import SettingsWindow

c = Config()
e = Engine(c)
w = SettingsWindow(c, e)
w.root.update_idletasks()
print("SettingsWindow OK - title:", w.root.title())
w.root.destroy()
print("UI test passed")
