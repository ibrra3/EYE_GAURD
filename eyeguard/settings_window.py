"""Tkinter settings window for EyeGuard (dark theme).

Runs on the main thread; the tray icon runs in its own thread. The tray
signals the window to show/quit via a thread-safe command queue, and the
window polls the engine state to refresh a live status bar.
"""

from __future__ import annotations

import os
import queue
import tkinter as tk
from tkinter import messagebox, ttk

from . import APP_NAME, TAGLINE
from .icon import build_icon

# palette
BG = "#161a22"
PANEL = "#1f242f"
FG = "#dbe1ea"
MUTED = "#8791a6"
ACCENT = "#5cb8ff"
ACCENT_DARK = "#0c1520"
DARK = "#0d1017"
WARM = "#ffb86c"


class SettingsWindow:
    def __init__(self, config, engine):
        self.config = config
        self.engine = engine
        self._cmd: "queue.Queue[str]" = queue.Queue()

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} Settings")
        self.root.geometry("660x620")
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        self._set_window_icon()
        self._apply_theme()
        self._build()

        self.root.withdraw()
        self.root.after(150, self._poll)

    # ---- lifecycle -------------------------------------------------------
    def run(self) -> None:
        self.root.mainloop()

    def hide(self) -> None:
        self.root.withdraw()

    def request_show(self) -> None:
        self._cmd.put("show")

    def request_quit(self) -> None:
        self._cmd.put("quit")

    def _poll(self) -> None:
        try:
            while True:
                cmd = self._cmd.get_nowait()
                if cmd == "show":
                    self.root.deiconify()
                    self.root.lift()
                elif cmd == "quit":
                    self.root.quit()
                    return
        except queue.Empty:
            pass
        self._refresh_status()
        self.root.after(500, self._poll)

    # ---- theme & icon ----------------------------------------------------
    def _set_window_icon(self) -> None:
        try:
            from PIL import ImageTk

            self._icon_photo = ImageTk.PhotoImage(build_icon(64))
            self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def _apply_theme(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            ".",
            background=BG,
            foreground=FG,
            fieldbackground=DARK,
            bordercolor=PANEL,
            lightcolor=PANEL,
            darkcolor=PANEL,
            troughcolor=PANEL,
            focuscolor=ACCENT,
            selectbackground=ACCENT,
            selectforeground=ACCENT_DARK,
            insertcolor=FG,
        )
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure(
            "Header.TLabel", background=BG, foreground=FG,
            font=("Segoe UI", 16, "bold"),
        )
        style.configure(
            "Tagline.TLabel", background=BG, foreground=MUTED,
            font=("Segoe UI", 9),
        )
        style.configure("TLabelframe", background=BG, bordercolor=PANEL)
        style.configure(
            "TLabelframe.Label", background=BG, foreground=ACCENT,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab", background=PANEL, foreground=FG,
            padding=(14, 7), borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", ACCENT)],
            foreground=[("selected", ACCENT_DARK)],
        )
        style.configure(
            "TButton", background=PANEL, foreground=FG, borderwidth=0,
            padding=(10, 5), focusthickness=0,
        )
        style.map(
            "TButton",
            background=[("active", ACCENT)],
            foreground=[("active", ACCENT_DARK)],
        )
        style.configure(
            "Accent.TButton", background=ACCENT, foreground=ACCENT_DARK,
            borderwidth=0, padding=(12, 6), font=("Segoe UI", 9, "bold"),
        )
        style.map("Accent.TButton", background=[("active", WARM)])
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TRadiobutton", background=BG, foreground=FG)
        style.map("TRadiobutton", background=[("active", BG)])
        style.configure(
            "TEntry", fieldbackground=DARK, foreground=FG, insertcolor=FG,
            bordercolor=PANEL,
        )
        style.configure(
            "TCombobox", fieldbackground=DARK, foreground=FG,
            background=PANEL, arrowcolor=FG,
        )
        style.configure(
            "Horizontal.TScale", background=BG, troughcolor=PANEL,
            bordercolor=PANEL, lightcolor=ACCENT, darkcolor=ACCENT,
        )
        style.configure(
            "Vertical.TScale", background=BG, troughcolor=PANEL,
        )

    # ---- UI construction -------------------------------------------------
    def _build(self) -> None:
        header = ttk.Frame(self.root, padding=(16, 14, 16, 6))
        header.pack(fill="x")

        try:
            from PIL import ImageTk

            self._header_photo = ImageTk.PhotoImage(build_icon(44))
            ttk.Label(header, image=self._header_photo).pack(side="left", padx=(0, 12))
        except Exception:
            pass

        title_box = ttk.Frame(header)
        title_box.pack(side="left", anchor="w")
        ttk.Label(title_box, text=APP_NAME, style="Header.TLabel").pack(anchor="w")
        ttk.Label(title_box, text=TAGLINE, style="Tagline.TLabel").pack(anchor="w")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=(2, 6))
        self._build_general(nb)
        self._build_brightness(nb)
        self._build_eye(nb)
        self._build_monitors(nb)
        self._build_rules(nb)

        status = tk.Frame(self.root, bg=PANEL)
        status.pack(fill="x", padx=12, pady=(0, 4))
        self.status_bar = tk.Label(
            status, text="", bg=PANEL, fg=FG, anchor="w",
            font=("Segoe UI", 9), padx=12, pady=6,
        )
        self.status_bar.pack(fill="x")

        footer = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        footer.pack(fill="x")
        ttk.Label(
            footer,
            text="Changes apply immediately and are saved to config.json.",
            style="Muted.TLabel",
        ).pack(side="left", anchor="s", pady=(0, 2))
        ttk.Button(
            footer, text="Apply & Save", style="Accent.TButton", command=self._save
        ).pack(side="right")

    def _build_general(self, nb) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="General")

        self.enabled_var = tk.BooleanVar(value=self.config.data.get("enabled", True))
        ttk.Checkbutton(
            f, text="Enable automatic brightness adjustment", variable=self.enabled_var
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.interval_var = tk.DoubleVar(
            value=self.config.data.get("interval_seconds", 1.5)
        )
        self._slider(f, 1, "Poll interval (sec)", self.interval_var, 0.5, 10.0)

        self.mode_var = tk.StringVar(
            value=self.config.data.get("luma_sample_mode", "foreground")
        )
        ttk.Label(f, text="Measure content from:").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Radiobutton(
            f, text="Active window", variable=self.mode_var, value="foreground"
        ).grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Radiobutton(
            f, text="Full screen", variable=self.mode_var, value="fullscreen"
        ).grid(row=3, column=1, sticky="w")

        self.step_var = tk.DoubleVar(
            value=self.config.brightness.get("max_step_per_sec", 60)
        )
        self._slider(f, 4, "Transition speed (%/sec)", self.step_var, 5.0, 200.0)

        # video pause
        vp = self.config.video_pause
        self.video_enabled_var = tk.BooleanVar(value=vp.get("enabled", True))
        ttk.Checkbutton(
            f, text="Pause auto-brightness while watching a video",
            variable=self.video_enabled_var,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(f, text="Video keywords (regex):").grid(
            row=6, column=0, sticky="w", pady=(4, 0)
        )
        self.video_match_var = tk.StringVar(value=vp.get("match", ""))
        ttk.Entry(f, textvariable=self.video_match_var).grid(
            row=6, column=1, columnspan=2, sticky="ew", pady=(4, 0)
        )

        # manual override
        manual = ttk.LabelFrame(f, text="Manual override", padding=10)
        manual.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        self.manual_var = tk.DoubleVar(value=50)
        ttk.Label(
            manual, text="Manual brightness (pins until the app changes):"
        ).pack(anchor="w")
        ttk.Scale(
            manual, from_=0, to=100, variable=self.manual_var,
            command=lambda _v: self._manual_changed(),
        ).pack(fill="x", pady=(4, 0))

    def _manual_changed(self) -> None:
        self.engine.set_manual_brightness(self.manual_var.get())

    def _build_brightness(self, nb) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="Brightness")

        self.dark_var = tk.DoubleVar(value=self.config.brightness.get("dark_target", 85))
        self.bright_var = tk.DoubleVar(value=self.config.brightness.get("bright_target", 40))
        self.min_var = tk.DoubleVar(value=self.config.brightness.get("min", 10))
        self.max_var = tk.DoubleVar(value=self.config.brightness.get("max", 100))

        ttk.Label(
            f, text="Dark content → higher brightness; white content → lower.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self._slider(f, 1, "Brightness for dark content", self.dark_var, 0, 100)
        self._slider(f, 2, "Brightness for white content", self.bright_var, 0, 100)
        self._slider(f, 3, "Minimum brightness", self.min_var, 0, 100)
        self._slider(f, 4, "Maximum brightness", self.max_var, 0, 100)

        self.software_var = tk.BooleanVar(
            value=self.config.brightness.get("use_software_for_internal", True)
        )
        ttk.Checkbutton(
            f,
            text="Overlay dimming for laptop panel (for dGPU/MUX laptops)",
            variable=self.software_var,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _build_eye(self, nb) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="Eye Protection")

        self.eye_enabled_var = tk.BooleanVar(value=self.config.eye.get("enabled", True))
        ttk.Checkbutton(
            f, text="Enable eye protection", variable=self.eye_enabled_var
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.eye_always_var = tk.BooleanVar(value=self.config.eye.get("always_on", False))
        ttk.Checkbutton(
            f, text="Always on (ignore content)", variable=self.eye_always_var
        ).grid(row=1, column=0, columnspan=3, sticky="w")

        self.eye_auto_var = tk.BooleanVar(value=self.config.eye.get("auto_trigger_white", True))
        ttk.Checkbutton(
            f, text="Auto-trigger on white/paper content", variable=self.eye_auto_var
        ).grid(row=2, column=0, columnspan=3, sticky="w")

        self.warmth_var = tk.DoubleVar(value=self.config.eye.get("warmth", 60))
        self._slider(f, 3, "Warmth (blue-light filter)", self.warmth_var, 0, 100)

        self.dim_var = tk.DoubleVar(value=self.config.eye.get("dim_percent", 15))
        self._slider(f, 4, "Extra dim while active (%)", self.dim_var, 0, 90)

        self.white_thresh_var = tk.DoubleVar(
            value=self.config.eye.get("white_luma_threshold", 200)
        )
        self._slider(f, 5, "White-content threshold", self.white_thresh_var, 100, 255)

    def _build_monitors(self, nb) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="Monitors")
        ttk.Label(
            f,
            text="Detected displays (read-only). Empty selection = control all.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        self.monitor_text = tk.Text(
            f, height=13, width=60, state="disabled", bg=DARK, fg=FG,
            insertbackground=FG, relief="flat", highlightthickness=0,
            font=("Consolas", 10),
        )
        self.monitor_text.pack(fill="both", expand=True)
        ttk.Button(f, text="Refresh", command=self._refresh_monitors).pack(
            anchor="w", pady=8
        )
        self._refresh_monitors()

    def _refresh_monitors(self) -> None:
        try:
            monitors = self.engine.brightness.list_monitors()
        except Exception as exc:  # pragma: no cover
            monitors = []
            messagebox.showerror(APP_NAME, f"Could not enumerate monitors:\n{exc}")
        lines = []
        for m in monitors:
            primary = " [primary]" if m.get("primary") else ""
            lines.append(f"{m.get('kind','?'):9s} {m.get('name','')}{primary}")
        self.monitor_text.configure(state="normal")
        self.monitor_text.delete("1.0", "end")
        self.monitor_text.insert("1.0", "\n".join(lines) or "No monitors detected.")
        self.monitor_text.configure(state="disabled")

    def _build_rules(self, nb) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="App Rules")

        ttk.Label(
            f, text="Rules match the process name + window title (regex).",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        self.rules_list = tk.Listbox(
            f, height=10, bg=DARK, fg=FG, selectbackground=ACCENT,
            selectforeground=ACCENT_DARK, relief="flat", highlightthickness=0,
            activestyle="none", font=("Consolas", 9),
        )
        self.rules_list.pack(fill="both", expand=True)
        self.rules_list.bind("<<ListboxSelect>>", self._rule_selected)

        form = ttk.Frame(f)
        form.pack(fill="x", pady=8)
        ttk.Label(form, text="Name:").grid(row=0, column=0, sticky="w")
        self.rule_name = ttk.Entry(form, width=18)
        self.rule_name.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(form, text="Match (regex):").grid(row=0, column=2, sticky="w")
        self.rule_match = ttk.Entry(form, width=28)
        self.rule_match.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(form, text="Brightness:").grid(row=1, column=0, sticky="w", pady=4)
        self.rule_bright = ttk.Entry(form, width=18)
        self.rule_bright.insert(0, "auto")
        self.rule_bright.grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(form, text="'auto' or 0-100").grid(row=1, column=2, sticky="w")

        self.rule_eye = tk.StringVar(value="auto")
        ttk.Label(form, text="Eye protection:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(
            form, textvariable=self.rule_eye, state="readonly",
            values=["auto", "on", "off"], width=16,
        ).grid(row=2, column=1, sticky="w", padx=4)

        btns = ttk.Frame(f)
        btns.pack(fill="x")
        ttk.Button(btns, text="Add", command=self._rule_add).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Update selected", command=self._rule_update).pack(
            side="left", padx=6
        )
        ttk.Button(btns, text="Delete selected", command=self._rule_delete).pack(
            side="left", padx=6
        )
        self._refresh_rules()

    def _refresh_rules(self) -> None:
        self.rules_list.delete(0, "end")
        for rule in self.config.rules:
            eye = rule.get("eye_protection")
            eye_txt = "auto" if eye is None else ("on" if eye else "off")
            self.rules_list.insert(
                "end",
                f"{rule.get('name','')}  |  {rule.get('match','')}  |  "
                f"brightness={rule.get('brightness','auto')}  eye={eye_txt}",
            )

    def _rule_selected(self, _event=None) -> None:
        sel = self.rules_list.curselection()
        if not sel:
            return
        rule = self.config.rules[sel[0]]
        self.rule_name.delete(0, "end")
        self.rule_name.insert(0, rule.get("name", ""))
        self.rule_match.delete(0, "end")
        self.rule_match.insert(0, rule.get("match", ""))
        self.rule_bright.delete(0, "end")
        self.rule_bright.insert(0, str(rule.get("brightness", "auto")))
        eye = rule.get("eye_protection")
        self.rule_eye.set("auto" if eye is None else ("on" if eye else "off"))

    def _rule_add(self) -> None:
        rule = self._rule_from_form()
        if not rule:
            return
        self.config.rules.append(rule)
        self._refresh_rules()

    def _rule_update(self) -> None:
        sel = self.rules_list.curselection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a rule first.")
            return
        rule = self._rule_from_form()
        if rule:
            self.config.rules[sel[0]] = rule
            self._refresh_rules()

    def _rule_delete(self) -> None:
        sel = self.rules_list.curselection()
        if not sel:
            return
        del self.config.rules[sel[0]]
        self._refresh_rules()

    def _rule_from_form(self):
        name = self.rule_name.get().strip()
        match = self.rule_match.get().strip()
        bright = self.rule_bright.get().strip()
        if not match:
            messagebox.showwarning(APP_NAME, "Match pattern is required.")
            return None
        try:
            bright_val = float(bright) if bright.lower() != "auto" else "auto"
        except ValueError:
            messagebox.showwarning(
                APP_NAME, "Brightness must be 'auto' or a number 0-100."
            )
            return None
        eye = self.rule_eye.get()
        eye_val = None if eye == "auto" else (eye == "on")
        return {
            "name": name or match,
            "match": match,
            "enabled": True,
            "brightness": bright_val,
            "eye_protection": eye_val,
        }

    # ---- helpers ---------------------------------------------------------
    def _slider(self, parent, row, label, var, from_, to) -> None:
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=5)
        value_label = ttk.Label(parent, text="", width=7, anchor="e")
        value_label.grid(row=row, column=1, sticky="e", pady=5)

        def update(_v):
            value_label.configure(text=f"{var.get():.1f}")

        var.trace_add("write", lambda *_: update(None))
        ttk.Scale(parent, from_=from_, to=to, variable=var, command=update).grid(
            row=row, column=2, sticky="ew", pady=5, padx=8
        )
        parent.columnconfigure(2, weight=1)
        update(None)

    def _save(self) -> None:
        b = self.config.brightness
        b["dark_target"] = round(self.dark_var.get(), 1)
        b["bright_target"] = round(self.bright_var.get(), 1)
        b["min"] = round(self.min_var.get(), 1)
        b["max"] = round(self.max_var.get(), 1)
        b["max_step_per_sec"] = round(self.step_var.get(), 1)
        b["use_software_for_internal"] = bool(self.software_var.get())

        e = self.config.eye
        e["enabled"] = bool(self.eye_enabled_var.get())
        e["always_on"] = bool(self.eye_always_var.get())
        e["auto_trigger_white"] = bool(self.eye_auto_var.get())
        e["warmth"] = round(self.warmth_var.get(), 1)
        e["dim_percent"] = round(self.dim_var.get(), 1)
        e["white_luma_threshold"] = round(self.white_thresh_var.get(), 1)

        vp = self.config.video_pause
        vp["enabled"] = bool(self.video_enabled_var.get())
        vp["match"] = self.video_match_var.get().strip()

        self.config.data["enabled"] = bool(self.enabled_var.get())
        self.config.data["interval_seconds"] = round(self.interval_var.get(), 2)
        self.config.data["luma_sample_mode"] = self.mode_var.get()

        self.config.save()

    def _refresh_status(self) -> None:
        s = self.engine.snapshot()
        app = s.get("app") or ""
        app_short = app.split("\\")[-1].split("/")[-1] if app else "—"
        lum = s.get("luminance")
        lum_txt = f"{lum:.0f}" if lum is not None else "—"
        bright = s.get("brightness")
        bright_txt = f"{bright}%" if bright is not None else "—"
        target = s.get("target")
        target_txt = f"{target:.0f}%" if target is not None else "—"
        eye = "ON" if s.get("eye_protection") else "off"
        video = "paused" if s.get("video") else "off"
        text = (
            f"App: {app_short}   •   Luminance: {lum_txt}   •   "
            f"Brightness: {bright_txt} (target {target_txt})   •   "
            f"Eye protection: {eye}   •   Video pause: {video}"
        )
        self.status_bar.configure(text=text)
