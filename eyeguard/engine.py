"""The adaptive-brightness engine.

A fast background thread (100 ms tick) transitions brightness smoothly toward a
target, while a slower poll (``interval_seconds``) recomputes that target from
the foreground app + screen luminance.

Brightness is applied per monitor:

* external displays -> DDC/CI backlight (hardware);
* the internal panel -> a translucent overlay dimmer by default (works even on
  dGPU/MUX laptops where WMI backlight control is a no-op), unless
  ``brightness.use_software_for_internal`` is disabled, in which case WMI is
  used.

While a configured video app/site is active (see ``video_pause``), brightness is
held steady so playback is never disturbed.
"""

from __future__ import annotations

import re
import threading
import time

from .brightness import BrightnessController
from .gamma import GammaController
from .mapping import (
    apply_dim,
    clamp,
    combined_ramp,
    is_white_content,
    luminance_to_target,
)
from .overlay import OverlayManager
from .screenluma import LumaSampler
from .windowinfo import foreground_process_name, foreground_window_title

TICK = 0.1  # seconds


class Engine:
    def __init__(self, config):
        self.config = config
        self.brightness = BrightnessController()
        self.gamma = GammaController()
        self.overlay = OverlayManager()
        self.sampler = LumaSampler()

        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

        self._manual_brightness: float | None = None
        self._manual_app: str | None = None
        self._current_brightness: float | None = self.brightness.get_current()
        self._target: float | None = self._current_brightness
        self._eye_active = False
        self._last_applied_brightness: int | None = None
        self._last_eye_active: bool | None = None

        self.state = {
            "app": "",
            "title": "",
            "rule": None,
            "luminance": None,
            "target": self._target,
            "brightness": self._current_brightness,
            "eye_protection": False,
            "video": False,
        }

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.overlay.start()
        self._thread = threading.Thread(
            target=self._run, name="eyeguard-engine", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        try:
            self.gamma.clear_all([m.device for m in self.brightness.monitors])
        except Exception:
            pass
        try:
            self.brightness.restore()
        except Exception:
            pass
        try:
            self.overlay.stop()
        except Exception:
            pass

    # ---- manual override -------------------------------------------------
    def set_manual_brightness(self, value: float) -> None:
        with self._lock:
            self._manual_brightness = clamp(value, 0, 100)
            self._manual_app = self.state.get("app")

    def resume_auto(self) -> None:
        with self._lock:
            self._manual_brightness = None
            self._manual_app = None

    def refresh_outputs(self) -> None:
        """Force the next tick to re-apply the current brightness/eye state."""
        self._last_applied_brightness = None
        self._last_eye_active = None

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.state)

    # ---- quick test ------------------------------------------------------
    def quick_test(self) -> None:
        """Briefly dim the laptop panel so the user can confirm it responds."""

        def _run() -> None:
            try:
                for mon in self.brightness.monitors:
                    if not mon.physical_handle:
                        self.overlay.set(mon.device, mon.rect, 25, 60)
                time.sleep(2.0)
            finally:
                self._refresh_outputs()

        threading.Thread(target=_run, name="eyeguard-quicktest", daemon=True).start()

    def _refresh_outputs(self) -> None:
        """Re-apply outputs from the current target (used after quick test)."""
        if self._target is None:
            self.gamma.clear_all([m.device for m in self.brightness.monitors])
            self.overlay.clear()
            return
        self._last_applied_brightness = None
        self._last_eye_active = None
        value = self._current_brightness if self._current_brightness is not None else self._target
        self._apply_outputs(int(round(value)), self._eye_active)

    # ---- internals -------------------------------------------------------
    def _run(self) -> None:
        last_poll = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            interval = self.config.data.get("interval_seconds", 1.5)
            if now - last_poll >= interval:
                try:
                    self._poll()
                except Exception:
                    pass
                last_poll = now
            try:
                self._step()
            except Exception:
                pass
            self._stop.wait(TICK)

    def _poll(self) -> None:
        cfg = self.config

        with self._lock:
            manual = self._manual_brightness
            manual_app = self._manual_app

        if not cfg.data.get("enabled", True):
            self._target = None
            self._eye_active = False
            self._last_applied_brightness = None
            self._last_eye_active = None
            self.gamma.clear_all([m.device for m in self.brightness.monitors])
            self.overlay.clear()
            with self._lock:
                self.state.update(
                    app="", title="", rule=None, luminance=None,
                    target=None, brightness=self._current_brightness,
                    eye_protection=False, video=False,
                )
            return

        app = foreground_process_name()
        title = foreground_window_title()
        rule = self._find_rule(app, title)

        # Hold brightness steady while watching a video.
        if self._is_video(app, title):
            if self._current_brightness is None:
                self._current_brightness = float(cfg.brightness.get("dark_target", 85))
            self._target = self._current_brightness
            with self._lock:
                self.state.update(
                    app=app,
                    title=title,
                    rule=rule.get("name") if rule else None,
                    luminance=None,
                    target=round(self._target, 1),
                    brightness=self._current_brightness,
                    eye_protection=self._eye_active,
                    video=True,
                )
            return

        lum = self.sampler.sample(cfg.data.get("luma_sample_mode", "foreground"))
        eye_active = self._resolve_eye_protection(rule, lum)

        if manual is not None and manual_app == app:
            target = manual
        elif rule and isinstance(rule.get("brightness"), (int, float)):
            target = float(rule["brightness"])
        elif lum is not None:
            target = luminance_to_target(lum, cfg.brightness)
        else:
            target = float(cfg.brightness.get("dark_target", 85))

        if eye_active:
            target = apply_dim(target, cfg.eye.get("dim_percent", 15))

        self._target = clamp(target, 0.0, 100.0)
        self._eye_active = eye_active

        with self._lock:
            self.state.update(
                app=app,
                title=title,
                rule=rule.get("name") if rule else None,
                luminance=round(lum, 1) if lum is not None else None,
                target=round(self._target, 1),
                brightness=self._current_brightness,
                eye_protection=eye_active,
                video=False,
            )

    def _step(self) -> None:
        target = self._target
        if target is None:
            return

        cur = self._current_brightness
        if cur is None:
            cur = target

        max_step = float(self.config.brightness.get("max_step_per_sec", 60.0))
        step = max_step * TICK
        diff = target - cur
        if abs(diff) <= 0.5 or abs(diff) <= step:
            new = target
        else:
            new = cur + (step if diff > 0 else -step)
        new = clamp(new, 0.0, 100.0)
        self._current_brightness = new

        rounded = int(round(new))
        if rounded != self._last_applied_brightness or self._eye_active != self._last_eye_active:
            self._apply_outputs(rounded, self._eye_active)
            self._last_applied_brightness = rounded
            self._last_eye_active = self._eye_active

        with self._lock:
            self.state["brightness"] = rounded

    def _apply_outputs(self, brightness: int, eye_active: bool) -> None:
        warmth = self.config.eye.get("warmth", 60) if eye_active else 0
        use_software = self.config.brightness.get("use_software_for_internal", True)
        only = self.config.data.get("monitors") or None

        for mon in self.brightness.monitors:
            if only and mon.name not in only and mon.device not in only:
                continue
            if mon.physical_handle:
                # External display: hardware backlight + warm tint via gamma.
                self.brightness.set_monitor_ddc(mon, brightness)
                self.gamma.apply(mon.device, combined_ramp(100, warmth))
            elif use_software:
                # Internal panel: overlay dim + warm tint. (A gamma ramp would
                # only affect the primary display, so an overlay is used here.)
                self.overlay.set(mon.device, mon.rect, brightness, warmth)
            else:
                # Internal panel: hardware WMI backlight + warm tint via gamma.
                self.brightness.set_wmi(brightness)
                self.gamma.apply(mon.device, combined_ramp(100, warmth))

    def _resolve_eye_protection(self, rule, lum) -> bool:
        eye = self.config.eye
        if rule and "eye_protection" in rule and rule["eye_protection"] is not None:
            return bool(rule["eye_protection"])
        if not eye.get("enabled", True):
            return False
        if eye.get("always_on", False):
            return True
        if eye.get("auto_trigger_white", True) and lum is not None:
            return is_white_content(lum, eye.get("white_luma_threshold", 200))
        return False

    def _is_video(self, app: str, title: str) -> bool:
        vp = self.config.video_pause
        if not vp.get("enabled", True):
            return False
        pattern = vp.get("match", "")
        if not pattern:
            return False
        try:
            return re.search(pattern, f"{app} {title}", re.IGNORECASE) is not None
        except re.error:
            return False

    def _find_rule(self, app: str, title: str):
        haystack = f"{app} {title}"
        for rule in self.config.rules:
            if not rule.get("enabled", True):
                continue
            pattern = rule.get("match", "")
            if not pattern:
                continue
            try:
                if re.search(pattern, haystack, re.IGNORECASE):
                    return rule
            except re.error:
                continue
        return None
