"""Read-only smoke test for the native Win32 layer.

Does NOT change brightness or apply any color filter. It only reads:

* the foreground process + title
* enumerated monitors (DDC/CI vs internal)
* current brightness
* a screen luminance sample

Run:  python scripts/smoke_test.py
"""

from eyeguard.brightness import BrightnessController
from eyeguard.screenluma import LumaSampler
from eyeguard.windowinfo import foreground_process_name, foreground_window_title


def main() -> None:
    print("Foreground process:", foreground_process_name() or "(none)")
    print("Foreground title:  ", foreground_window_title() or "(none)")

    controller = BrightnessController()
    print("\nMonitors:")
    for m in controller.list_monitors():
        primary = " [primary]" if m["primary"] else ""
        print(f"  {m['kind']:8s} {m['name']}{primary}")

    current = controller.get_current()
    print("\nCurrent brightness:", current if current is not None else "(unavailable)")

    sampler = LumaSampler()
    lum_fg = sampler.sample("foreground")
    lum_fs = sampler.sample("fullscreen")
    print(f"Luminance (foreground): {lum_fg}")
    print(f"Luminance (fullscreen): {lum_fs}")


if __name__ == "__main__":
    main()
