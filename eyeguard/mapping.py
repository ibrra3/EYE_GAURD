"""Pure, dependency-free mapping functions.

These translate screen luminance and user settings into target brightness
values and warm color gamma ramps. They are kept side-effect free so they can
be unit-tested without touching any display hardware.
"""

from __future__ import annotations


def clamp(value: float, low: float, high: float) -> float:
    """Clamp *value* to the inclusive range [low, high]."""
    return max(low, min(high, value))


def luminance_to_target(luminance: float, bright_cfg: dict) -> float:
    """Map average screen luminance (0..255) to a target brightness (0..100).

    Dark content (luminance ~0) maps to ``dark_target`` (higher brightness);
    white/paper content (luminance ~255) maps to ``bright_target`` (lower
    brightness). A smoothstep curve keeps the transition natural in the middle.
    """
    t = clamp(luminance, 0.0, 255.0) / 255.0
    t = t * t * (3.0 - 2.0 * t)  # smoothstep: flat near the ends, smooth middle
    dark = float(bright_cfg.get("dark_target", 85))
    bright = float(bright_cfg.get("bright_target", 40))
    target = dark + (bright - dark) * t
    return clamp(target, float(bright_cfg.get("min", 10)), float(bright_cfg.get("max", 100)))


def apply_dim(target: float, dim_percent: float) -> float:
    """Reduce *target* brightness by *dim_percent* (0..90)."""
    return clamp(target * (1.0 - clamp(dim_percent, 0, 90) / 100.0), 0.0, 100.0)


def is_white_content(luminance: float, threshold: float) -> bool:
    """Return True when content is bright/white enough to trigger eye protection."""
    return luminance >= threshold


def identity_ramp() -> list[int]:
    """Return a neutral gamma ramp (R, G, B as 0..65535 words, 3*256 entries)."""
    ramp: list[int] = []
    for _ in range(3):
        for i in range(256):
            ramp.append(i * 257)
    return ramp


def warm_ramp(warmth: int) -> list[int]:
    """Build a 3*256 gamma ramp that shifts the display toward a warm tone.

    ``warmth`` ranges 0 (neutral) to 100 (warmest / least blue). Red is left
    untouched, green is reduced modestly, and blue is reduced the most — the
    standard blue-light / f.lux-style approach.
    """
    warmth = clamp(int(warmth), 0, 100)
    blue_factor = 1.0 - 0.55 * (warmth / 100.0)
    green_factor = 1.0 - 0.20 * (warmth / 100.0)

    ramp: list[int] = []
    for i in range(256):  # red
        ramp.append(clamp(i * 257, 0, 65535))
    for i in range(256):  # green
        ramp.append(clamp(round(i * 257 * green_factor), 0, 65535))
    for i in range(256):  # blue
        ramp.append(clamp(round(i * 257 * blue_factor), 0, 65535))
    return ramp


def brightness_to_scale(brightness: float) -> float:
    """Map brightness 0..100 to a gamma scale factor (0.05..1.0).

    A small floor keeps the screen from going fully black at 0.
    """
    b = clamp(brightness, 0.0, 100.0) / 100.0
    return 0.05 + 0.95 * b


def combined_ramp(brightness: float, warmth: int) -> list[int]:
    """Gamma ramp combining software brightness (dim) and a warm color shift.

    ``brightness`` 100 + ``warmth`` 0 equals identity. Lower brightness dims all
    channels; higher warmth reduces green/blue. Used for per-monitor software
    dimming (e.g. the internal panel on dGPU/MUX laptops where WMI backlight is
    a no-op).
    """
    scale = brightness_to_scale(brightness)
    warmth = clamp(int(warmth), 0, 100)
    red = scale
    green = scale * (1.0 - 0.20 * (warmth / 100.0))
    blue = scale * (1.0 - 0.55 * (warmth / 100.0))

    ramp: list[int] = []
    for i in range(256):  # red
        ramp.append(clamp(round(i * 257 * red), 0, 65535))
    for i in range(256):  # green
        ramp.append(clamp(round(i * 257 * green), 0, 65535))
    for i in range(256):  # blue
        ramp.append(clamp(round(i * 257 * blue), 0, 65535))
    return ramp
