"""Unit tests for the pure mapping logic (no display hardware required)."""

from eyeguard.mapping import (
    apply_dim,
    brightness_to_scale,
    clamp,
    combined_ramp,
    identity_ramp,
    is_white_content,
    luminance_to_target,
    warm_ramp,
)


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(11, 0, 10) == 10


def test_luminance_mapping_monotonic_and_bounded():
    cfg = {"dark_target": 85, "bright_target": 40, "min": 10, "max": 100}
    dark = luminance_to_target(0, cfg)
    white = luminance_to_target(255, cfg)
    assert dark == 85.0
    assert white == 40.0
    # monotonic non-increasing as luminance rises
    prev = dark
    for lum in range(0, 256, 5):
        val = luminance_to_target(lum, cfg)
        assert 40.0 <= val <= 85.0
        assert val <= prev + 1e-9
        prev = val


def test_dim():
    assert apply_dim(80, 25) == 60.0
    assert apply_dim(100, 0) == 100.0
    assert abs(apply_dim(50, 90) - 5.0) < 1e-9


def test_white_detection():
    assert is_white_content(220, 200)
    assert not is_white_content(180, 200)


def test_ramps():
    ident = identity_ramp()
    assert len(ident) == 768
    assert ident[0] == 0
    assert ident[255] == 65535

    warm = warm_ramp(100)
    assert len(warm) == 768
    # blue channel (index 512..767) must be reduced vs identity
    assert warm[512 + 255] < ident[512 + 255]
    # red channel untouched
    assert warm[255] == ident[255]


def test_brightness_to_scale():
    assert brightness_to_scale(100) == 1.0
    assert brightness_to_scale(0) == 0.05
    assert 0.0 < brightness_to_scale(50) < 1.0


def test_combined_ramp():
    ident = identity_ramp()
    assert combined_ramp(100, 0) == ident
    dimmed = combined_ramp(50, 0)
    assert len(dimmed) == 768
    assert dimmed[255] < ident[255]  # dimmed red < full red
    warm = combined_ramp(100, 100)
    assert warm[512 + 255] < ident[512 + 255]  # blue reduced


if __name__ == "__main__":
    test_clamp()
    test_luminance_mapping_monotonic_and_bounded()
    test_dim()
    test_white_detection()
    test_ramps()
    test_brightness_to_scale()
    test_combined_ramp()
    print("All mapping tests passed.")
