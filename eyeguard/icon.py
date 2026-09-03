"""EyeGuard application icon: an eye inside a screen.

Drawn programmatically with Pillow (no image asset needed). Supersampled 4x
for smooth edges, then downscaled with Lanczos.
"""

from __future__ import annotations


def build_icon(size: int = 64):
    """Return an RGBA PIL image of the EyeGuard logo at *size* x *size*."""
    from PIL import Image, ImageDraw

    ss = 4  # supersample factor
    w = size * ss
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # palette
    bezel = (52, 58, 74, 255)
    screen = (13, 17, 28, 255)
    sclera = (242, 246, 251, 255)
    iris_top = (112, 196, 255, 255)
    iris_bottom = (46, 120, 220, 255)
    pupil = (8, 12, 24, 255)
    highlight = (255, 255, 255, 235)
    stand = (66, 72, 92, 255)

    def f(x: float) -> float:
        return x * w

    # monitor bezel + screen
    d.rounded_rectangle((f(0.08), f(0.04), f(0.92), f(0.72)), radius=f(0.055), fill=bezel)
    d.rounded_rectangle((f(0.13), f(0.09), f(0.87), f(0.67)), radius=f(0.035), fill=screen)

    # eye (centered inside the screen)
    cx, cy = f(0.5), f(0.38)
    rx, ry = f(0.235), f(0.155)
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=sclera)

    # iris with a subtle two-tone (top color over bottom)
    ir = f(0.135)
    d.ellipse((cx - ir, cy - ir, cx + ir, cy + ir), fill=iris_top)
    d.pieslice((cx - ir, cy - ir, cx + ir, cy + ir), 0, 180, fill=iris_bottom)

    # pupil
    pr = f(0.058)
    d.ellipse((cx - pr, cy - pr, cx + pr, cy + pr), fill=pupil)

    # highlight
    hr = f(0.030)
    hx, hy = cx + f(0.055), cy - f(0.065)
    d.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=highlight)

    # stand
    d.polygon(
        [(f(0.42), f(0.72)), (f(0.58), f(0.72)), (f(0.55), f(0.86)), (f(0.45), f(0.86))],
        fill=stand,
    )
    d.rounded_rectangle((f(0.34), f(0.86), f(0.66), f(0.90)), radius=f(0.02), fill=stand)

    return img.resize((size, size), Image.LANCZOS)
