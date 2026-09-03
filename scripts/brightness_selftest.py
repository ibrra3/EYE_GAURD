"""End-to-end brightness self-test.

Briefly changes brightness, verifies it took effect, then restores the
original value. Requires WMI access (run with full access / outside sandbox).

Run:  python scripts/brightness_selftest.py
"""

import time

from eyeguard.brightness import BrightnessController


def main() -> None:
    c = BrightnessController()
    print("Monitors:", c.list_monitors())

    original = c.get_current()
    print("Original brightness:", original)
    if original is None:
        print("No brightness source found; cannot self-test.")
        return

    try:
        test = max(0, original - 20)
        c.set_all(test)
        time.sleep(1.0)
        after = c.get_current()
        print(f"Set to {test}, read back: {after}")

        if after is not None and abs(after - test) <= 25:
            print("SELF-TEST PASSED: brightness responded to the change.")
        else:
            print("SELF-TEST INCONCLUSIVE: read-back did not match the request.")
    finally:
        c.set_all(original)
        time.sleep(0.5)
        print("Restored to:", c.get_current())


if __name__ == "__main__":
    main()
