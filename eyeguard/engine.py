"""The adaptive-brightness engine.

A fast background thread (100 ms tick) transitions each display's brightness
smoothly toward its own target, while a slower poll (``interval_seconds``)
recomputes those targets from the foreground app + screen luminance.

Integrates the optional comfort features:

* per-display profiles (``Config.brightness_for`` / ``Config.eye_for``);
* idle (AFK) dimming;
* ambient-light blending (when a light sensor is present);
* a time schedule that auto-switches comfort modes;
* per-app brightness ranges;
* monitor hot-plug detection;
* warm tint on every display (gamma on the primary, overlay elsewhere).

Brightness is applied per monitor: external displays use DDC/CI backlight, the
internal panel uses a translucent overlay dimmer (or WMI). While a configured
video app/site is active, brightness is held steady.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime

from .ambient import AmbientLightSensor, lux_to_luma
from .brightness import BrightnessController
from .gamma import GammaController
from .idle import idle_seconds
from .mapping import (
    apply_dim,
    clamp,
    combined_ramp,
    is_white_content,
    luminance_to_target,
)
from .notify import show as notify
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
        self.ambient = AmbientLightSensor(
            config.data.get("ambient_light", {}).get("refresh_seconds", 30)
        )

        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

        self._manual_brightness: float | None = None
        self._manual_app: str | None = None

        self._currents: dict[str, float] = {}
        self._targets: dict[str, float] = {}
        self._eyes: dict[str, bool] = {}
        self._last_brightness: dict[str, int] = {}
        self._last_eye: dict[str, bool] = {}

        self._idle_active = False
        self._video_active = False
        self._last_scheduled_mode: str | None = None

        start = self.brightness.get_current()
        for mon in self.brightness.monitors:
            self._currents[mon.device] = float(start) if start is not None else None
            self._targets[mon.device] = self._currents[mon.device]
            self._eyes[mon.device] = False

        self.state = {
            "app": "",
            "title": "",
            "rule": None,
            "luminance": None,
            "video": False,
            "idle": False,
            "linked": self.config.link_displays,
            "monitors": [],
        }

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.overlay.start()
        self._ensure_ambient()
        self._thread = threading.Thread(
            target=self._run, name="eyeguard-engine", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        try:
            self.ambient.stop()
        except Exception:
            pass
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
        """Force the next tick to re-apply every display's current state."""
        self._last_brightness = {}
        self._last_eye = {}

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
                self.refresh_outputs()

        threading.Thread(target=_run, name="eyeguard-quicktest", daemon=True).start()

    # ---- internals -------------------------------------------------------
    def _in_scope(self, mon) -> bool:
        only = self.config.data.get("monitors") or None
        if not only:
            return True
        return mon.name in only or mon.device in only

    def _ensure_ambient(self) -> None:
        acfg = self.config.data.get("ambient_light", {})
        running = self.ambient._thread is not None and self.ambient._thread.is_alive()
        if acfg.get("enabled") and not running:
            self.ambient.start()
        elif not acfg.get("enabled") and running:
            self.ambient.stop()

    def _run(self) -> None:
        last_poll = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            interval = self.config.data.get("interval_seconds", 1.5)
            if now - last_poll >= interval:
                try:
                    self._check_displays()
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
        self._ensure_ambient()
        self._apply_schedule()

        monitors = self.brightness.monitors

        with self._lock:
            manual = self._manual_brightness
            manual_app = self._manual_app

        if not cfg.data.get("enabled", True):
            for m in monitors:
                self._eyes[m.device] = False
            self._targets = {}
            self._last_brightness = {}
            self._last_eye = {}
            self._idle_active = False
            self._video_active = False
            self.gamma.clear_all([m.device for m in monitors])
            self.overlay.clear()
            with self._lock:
                self.state.update(
                    app="", title="", rule=None, luminance=None,
                    video=False, idle=False, linked=cfg.link_displays,
                    monitors=self._monitor_summary(),
                )
            return

        app = foreground_process_name()
        title = foreground_window_title()
        rule = self._find_rule(app, title)

        # Hold brightness steady while watching a video.
        if self._is_video(app, title):
            if not self._video_active:
                notify("EyeGuard", "Video detected — holding brightness")
            self._video_active = True
            for m in monitors:
                if not self._in_scope(m):
                    continue
                dev = m.device
                cur = self._currents.get(dev)
                if cur is None:
                    cur = float(cfg.brightness_for(dev).get("dark_target", 85))
                    self._currents[dev] = cur
                self._targets[dev] = cur
            with self._lock:
                self.state.update(
                    app=app, title=title,
                    rule=rule.get("name") if rule else None,
                    luminance=None, video=True, idle=self._idle_active,
                    linked=cfg.link_displays, monitors=self._monitor_summary(),
                )
            return
        self._video_active = False

        # Idle (AFK) dimming.
        idle_cfg = cfg.data.get("idle", {})
        if idle_cfg.get("enabled") and idle_seconds() >= int(idle_cfg.get("minutes", 10)) * 60:
            if not self._idle_active:
                notify("EyeGuard", "You're away — dimming the screen")
            self._idle_active = True
            dim_to = float(clamp(idle_cfg.get("dim_to", 25), 0, 100))
            for m in monitors:
                if self._in_scope(m):
                    self._targets[m.device] = dim_to
            with self._lock:
                self.state.update(
                    app=app, title=title,
                    rule=rule.get("name") if rule else None,
                    luminance=None, video=False, idle=True,
                    linked=cfg.link_displays, monitors=self._monitor_summary(),
                )
            return
        if self._idle_active:
            notify("EyeGuard", "Welcome back — restoring brightness")
        self._idle_active = False

        lum = self.sampler.sample(cfg.data.get("luma_sample_mode", "foreground"))
        lum = self._blend_ambient(lum)

        rb = rule.get("brightness") if rule else None

        for m in monitors:
            if not self._in_scope(m):
                continue
            dev = m.device
            bcfg = cfg.brightness_for(dev)
            ecfg = cfg.eye_for(dev)
            eye_active = self._resolve_eye_protection(rule, lum, ecfg)

            if manual is not None and manual_app == app:
                target = manual
            elif isinstance(rb, (list, tuple)) and len(rb) == 2:
                target = (
                    luminance_to_target(lum, bcfg)
                    if lum is not None
                    else float(bcfg.get("dark_target", 85))
                )
                target = clamp(target, float(rb[0]), float(rb[1]))
            elif isinstance(rb, (int, float)):
                target = float(rb)
            elif lum is not None:
                target = luminance_to_target(lum, bcfg)
            else:
                target = float(bcfg.get("dark_target", 85))

            if eye_active:
                target = apply_dim(target, ecfg.get("dim_percent", 15))

            self._targets[dev] = clamp(target, 0.0, 100.0)
            self._eyes[dev] = eye_active

        with self._lock:
            self.state.update(
                app=app,
                title=title,
                rule=rule.get("name") if rule else None,
                luminance=round(lum, 1) if lum is not None else None,
                video=False,
                idle=False,
                linked=cfg.link_displays,
                monitors=self._monitor_summary(),
            )

    def _step(self) -> None:
        max_step = float(self.config.brightness.get("max_step_per_sec", 60.0))
        step = max_step * TICK

        for mon in self.brightness.monitors:
            if not self._in_scope(mon):
                continue
            dev = mon.device
            target = self._targets.get(dev)
            if target is None:
                continue
            cur = self._currents.get(dev)
            if cur is None:
                cur = target

            diff = target - cur
            if abs(diff) <= 0.5 or abs(diff) <= step:
                new = target
            else:
                new = cur + (step if diff > 0 else -step)
            new = clamp(new, 0.0, 100.0)
            self._currents[dev] = new

            rounded = int(round(new))
            eye = self._eyes.get(dev, False)
            if rounded != self._last_brightness.get(dev) or eye != self._last_eye.get(dev):
                self._apply_monitor(mon, rounded, eye)
                self._last_brightness[dev] = rounded
                self._last_eye[dev] = eye

        with self._lock:
            self.state["monitors"] = self._monitor_summary()

    def _apply_monitor(self, mon, brightness: int, eye_active: bool) -> None:
        ecfg = self.config.eye_for(mon.device)
        warmth = ecfg.get("warmth", 60) if eye_active else 0
        use_software = self.config.brightness.get("use_software_for_internal", True)

        if mon.physical_handle:
            # External display: hardware backlight + warm tint.
            self.brightness.set_monitor_ddc(mon, brightness)
            self._apply_warm(mon, warmth)
        elif use_software:
            # Internal panel: overlay dim + warm tint.
            self.overlay.set(mon.device, mon.rect, brightness, warmth)
        else:
            # Internal panel: hardware WMI backlight + warm tint.
            self.brightness.set_wmi(brightness)
            self._apply_warm(mon, warmth)

    def _apply_warm(self, mon, warmth: int) -> None:
        if mon.primary:
            # Gamma ramps only take effect on the primary display.
            self.gamma.apply(mon.device, combined_ramp(100, warmth))
        else:
            # Secondary displays get the tint via a translucent overlay.
            self.overlay.set(mon.device, mon.rect, 100, warmth)

    def _blend_ambient(self, lum):
        acfg = self.config.data.get("ambient_light", {})
        if not acfg.get("enabled"):
            return lum
        lux = self.ambient.get_lux()
        if lux is None:
            return lum
        aluma = lux_to_luma(lux, acfg.get("max_lux", 1000))
        weight = clamp(acfg.get("weight", 0.5), 0.0, 1.0)
        if lum is None:
            return aluma
        return lum * (1.0 - weight) + aluma * weight

    def _apply_schedule(self) -> None:
        scfg = self.config.data.get("schedule", {})
        if not scfg.get("enabled"):
            self._last_scheduled_mode = None
            return
        mode = self._scheduled_mode()
        if mode and mode != self._last_scheduled_mode:
            self._last_scheduled_mode = mode
            if self.config.apply_mode(mode):
                self.refresh_outputs()
                notify("EyeGuard", f"Scheduled mode: {mode.replace('_', ' ').title()}")

    def _scheduled_mode(self) -> str | None:
        entries = self.config.data.get("schedule", {}).get("entries", [])
        valid = sorted(
            [e for e in entries if e.get("time") and e.get("mode")],
            key=lambda e: e["time"],
        )
        if not valid:
            return None
        now = datetime.now().strftime("%H:%M")
        active = None
        for e in valid:
            if e["time"] <= now:
                active = e["mode"]
            else:
                break
        if active is None:
            active = valid[-1]["mode"]  # carry over from the previous day
        return active

    def _check_displays(self) -> None:
        try:
            devices = self.brightness.list_devices()
        except Exception:
            return
        current = {m.device for m in self.brightness.monitors}
        if devices == current:
            return
        self.brightness.refresh()
        known = {m.device for m in self.brightness.monitors}
        for mon in self.brightness.monitors:
            dev = mon.device
            if dev not in self._currents:
                self._currents[dev] = None
                self._targets[dev] = None
                self._eyes[dev] = False
                self._last_brightness.pop(dev, None)
                self._last_eye.pop(dev, None)
        for dev in list(self._currents):
            if dev not in known:
                self._currents.pop(dev, None)
                self._targets.pop(dev, None)
                self._eyes.pop(dev, None)
                self._last_brightness.pop(dev, None)
                self._last_eye.pop(dev, None)
        notify("EyeGuard", "Display configuration changed")

    def _monitor_summary(self) -> list:
        out = []
        for m in self.brightness.monitors:
            dev = m.device
            cur = self._currents.get(dev)
            tgt = self._targets.get(dev)
            out.append(
                {
                    "device": dev,
                    "name": m.name or dev,
                    "kind": m.kind,
                    "brightness": int(round(cur)) if cur is not None else None,
                    "target": int(round(tgt)) if tgt is not None else None,
                    "eye": bool(self._eyes.get(dev, False)),
                }
            )
        return out

    def _resolve_eye_protection(self, rule, lum, ecfg: dict) -> bool:
        if rule and "eye_protection" in rule and rule["eye_protection"] is not None:
            return bool(rule["eye_protection"])
        if not ecfg.get("enabled", True):
            return False
        if ecfg.get("always_on", False):
            return True
        if ecfg.get("auto_trigger_white", True) and lum is not None:
            return is_white_content(lum, ecfg.get("white_luma_threshold", 200))
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
