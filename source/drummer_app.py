#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Drummer Studio Contributors
"""Drummer Studio — free open-source drum kit player, mixer, and groove browser."""

from __future__ import annotations

import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from kit_ui import (
    PAD_ALIASES_ENGINE,
    KitRegion,
    KitVisual,
    load_kit_visual,
    load_mixer,
)
from library_parser import list_drumsets, load_kit
from library_scanner import DetectedLibrary, detect_all, load_catalog
from midi_grooves import GrooveLibrary, GroovePlayer
from sampler_engine import SamplerEngine
from sfz_parser import list_drum_replacer_kits, load_drum_replacer_kit

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

APP_NAME = "Drummer Studio"
APP_VERSION = "2.0.0"
PUBLISHER = "Drummer Studio Contributors"
LICENSE_NAME = "MIT"
LICENSE_URL = "https://opensource.org/licenses/MIT"

THEME = {
    "bg": "#0f0f12",
    "panel": "#1a1a22",
    "panel2": "#22222c",
    "accent": "#e8620a",
    "accent_dim": "#b84a08",
    "text": "#f4f4f6",
    "muted": "#7a7a8c",
    "mixer_bg": "#141418",
    "fader_trough": "#2e2e3a",
    "highlight": "#ff9940",
}

KEY_BINDINGS = {
    "g": ("hatsCL", 92),
    "h": ("hatsO1", 96),
    "j": ("ride4", 88),
    "f": ("snareR", 112),
    "1": ("tom1L", 102),
    "2": ("tom1R", 98),
    "3": ("hsnareR", 90),
}


class KitCanvas(tk.Canvas):
    """Clickable drum kit photo (EZdrummer-style main view)."""

    def __init__(self, master, on_hit, **kwargs) -> None:
        super().__init__(master, highlightthickness=0, **kwargs)
        self.on_hit = on_hit
        self.visual: KitVisual | None = None
        self._photo = None
        self._scale = 1.0
        self._offset_x = 0
        self._offset_y = 0
        self._flash_id: str | None = None
        self.bind("<Button-1>", self._click)
        self.bind("<Configure>", lambda _e: self._redraw())

    def load_visual(self, visual: KitVisual) -> None:
        self.visual = visual
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        if not self.visual:
            self._draw_placeholder()
            return

        cw = max(200, self.winfo_width())
        ch = max(200, self.winfo_height())
        iw, ih = self.visual.canvas_width, self.visual.canvas_height
        self._scale = min(cw / iw, ch / ih, 1.0)
        dw, dh = int(iw * self._scale), int(ih * self._scale)
        self._offset_x = (cw - dw) // 2
        self._offset_y = (ch - dh) // 2

        if self.visual.image_path and Image and ImageTk:
            try:
                img = Image.open(self.visual.image_path).convert("RGB")
                img = img.resize((dw, dh), Image.Resampling.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
                self.create_image(self._offset_x, self._offset_y, anchor="nw", image=self._photo)
            except OSError:
                self._draw_placeholder()
        else:
            self._draw_kit_silhouette(dw, dh)

        for region in self.visual.regions:
            x1 = self._offset_x + int(region.x * self._scale)
            y1 = self._offset_y + int(region.y * self._scale)
            x2 = x1 + int(region.width * self._scale)
            y2 = y1 + int(region.height * self._scale)
            self.create_rectangle(x1, y1, x2, y2, outline="", fill="", tags=("hit", region.piece))

    def _draw_placeholder(self) -> None:
        w, h = max(200, self.winfo_width()), max(200, self.winfo_height())
        self.create_rectangle(0, 0, w, h, fill=THEME["panel2"], outline="")
        self.create_text(w // 2, h // 2, text="Load a kit to see drums", fill=THEME["muted"], font=("Segoe UI", 11))

    def _draw_kit_silhouette(self, dw: int, dh: int) -> None:
        ox, oy = self._offset_x, self._offset_y
        self.create_oval(ox + dw * 0.35, oy + dh * 0.55, ox + dw * 0.65, oy + dh * 0.95, fill="#2a2218", outline="#3d3428")
        self.create_oval(ox + dw * 0.38, oy + dh * 0.25, ox + dw * 0.62, oy + dh * 0.55, fill="#3a3a44", outline="#505060")
        self.create_text(ox + dw // 2, oy + dh - 12, text="Generic Kit", fill=THEME["muted"], font=("Segoe UI", 9))

    def _click(self, event) -> None:
        if not self.visual:
            return
        lx = (event.x - self._offset_x) / self._scale
        ly = (event.y - self._offset_y) / self._scale
        for region in self.visual.regions:
            if region.x <= lx <= region.x + region.width and region.y <= ly <= region.y + region.height:
                self._flash(region)
                for pad in region.pads:
                    if self.on_hit(pad, 105):
                        return
                return

    def _flash(self, region: KitRegion) -> None:
        if self._flash_id:
            self.delete(self._flash_id)
        x1 = self._offset_x + int(region.x * self._scale)
        y1 = self._offset_y + int(region.y * self._scale)
        x2 = x1 + int(region.width * self._scale)
        y2 = y1 + int(region.height * self._scale)
        self._flash_id = self.create_rectangle(x1, y1, x2, y2, outline=THEME["highlight"], width=2)
        self.after(150, lambda: self.delete(self._flash_id) if self._flash_id else None)


class DrummerStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1280x780")
        self.minsize(1024, 680)
        self.configure(bg=THEME["bg"])

        self.engine = SamplerEngine()
        self.groove_library = GrooveLibrary()
        self.groove_player = GroovePlayer(self.engine.trigger_note)
        self.detected: list[DetectedLibrary] = detect_all()
        self.current_detected = self.detected[0] if self.detected else None
        self.current_lib = self.detected[0].path if self.detected else None
        self.midi_root = self.detected[0].midi_root if self.detected else None
        self.mixer_channels: list = []
        self.mixer_presets: dict = {}
        self.fader_vars: dict[str, tk.DoubleVar] = {}
        self._piece_click_index: dict[str, int] = {}

        self._build_styles()
        self._build_layout()
        self._bind_keys()
        self.after(200, self.bootstrap)

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=THEME["bg"], foreground=THEME["text"], font=("Segoe UI", 9))
        style.configure("TFrame", background=THEME["bg"])
        style.configure("Toolbar.TFrame", background=THEME["panel"])
        style.configure("TLabel", background=THEME["bg"], foreground=THEME["text"])
        style.configure("Toolbar.TLabel", background=THEME["panel"], foreground=THEME["muted"])
        style.configure("Title.TLabel", background=THEME["panel"], foreground=THEME["text"], font=("Segoe UI", 14, "bold"))
        style.configure("TCombobox", fieldbackground=THEME["panel2"], background=THEME["panel2"])
        style.configure("TNotebook", background=THEME["bg"], tabmargins=[2, 4, 2, 0])
        style.configure("TNotebook.Tab", padding=[14, 6], background=THEME["panel"], foreground=THEME["muted"])
        style.map("TNotebook.Tab", background=[("selected", THEME["panel2"])], foreground=[("selected", THEME["text"])])
        style.configure("Treeview", background=THEME["panel2"], fieldbackground=THEME["panel2"], foreground=THEME["text"], rowheight=24)
        style.configure("Treeview.Heading", background=THEME["panel"], foreground=THEME["text"])

    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(12, 8))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text=APP_NAME, style="Title.TLabel").pack(side="left", padx=(4, 16))

        ttk.Label(toolbar, text="Library", style="Toolbar.TLabel").pack(side="left")
        self.library_var = tk.StringVar()
        self.library_combo = ttk.Combobox(toolbar, textvariable=self.library_var, width=36, state="readonly")
        self.library_combo.pack(side="left", padx=(6, 12))
        self.library_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_library_change())

        ttk.Label(toolbar, text="Kit", style="Toolbar.TLabel").pack(side="left")
        self.kit_var = tk.StringVar()
        self.kit_combo = ttk.Combobox(toolbar, textvariable=self.kit_var, width=22, state="readonly")
        self.kit_combo.pack(side="left", padx=(6, 12))
        self.kit_combo.bind("<<ComboboxSelected>>", lambda _e: self.load_selected_kit())

        ttk.Label(toolbar, text="Mix Preset", style="Toolbar.TLabel").pack(side="left")
        self.preset_var = tk.StringVar(value="Default")
        self.preset_combo = ttk.Combobox(toolbar, textvariable=self.preset_var, width=12, state="readonly")
        self.preset_combo.pack(side="left", padx=(6, 12))
        self.preset_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_mix_preset())

        ttk.Button(toolbar, text="Rescan Libraries", command=self.rescan).pack(side="right", padx=4)
        ttk.Button(toolbar, text="About", command=self._show_about).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Sources", command=self._show_sources_dialog).pack(side="right")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(toolbar, textvariable=self.status_var, style="Toolbar.TLabel").pack(side="right", padx=(0, 16))

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        kit_panel = ttk.Frame(main, style="Toolbar.TFrame")
        grooves_panel = ttk.Frame(main)
        main.add(kit_panel, weight=3)
        main.add(grooves_panel, weight=2)

        ttk.Label(kit_panel, text="DRUM KIT", style="Toolbar.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(6, 0))
        self.kit_canvas = KitCanvas(kit_panel, on_hit=self.hit_pad, bg=THEME["panel2"], bd=0)
        self.kit_canvas.pack(fill="both", expand=True, padx=6, pady=6)

        hint = ttk.Label(kit_panel, text="Click drums on the kit  •  Space kick  F snare  G/H hats  1/2/3 toms  J ride", style="Toolbar.TLabel")
        hint.pack(anchor="w", padx=10, pady=(0, 6))

        self._build_groove_panel(grooves_panel)
        self._build_mixer()

    def _build_groove_panel(self, parent) -> None:
        ttk.Label(parent, text="GROOVE BROWSER", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=(6, 4))
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=(0, 4))
        self.groove_search = tk.StringVar()
        self.groove_search.trace_add("write", lambda *_: self.refresh_groove_list())
        ttk.Entry(top, textvariable=self.groove_search).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Play", command=self.play_selected_groove).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Stop", command=self.groove_player.stop).pack(side="right", padx=(4, 0))

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, padx=4, pady=4)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.groove_tree = ttk.Treeview(body, columns=("genre", "bpm", "name"), show="headings", selectmode="browse")
        self.groove_tree.heading("genre", text="Genre")
        self.groove_tree.heading("bpm", text="BPM")
        self.groove_tree.heading("name", text="Groove")
        self.groove_tree.column("genre", width=100)
        self.groove_tree.column("bpm", width=70)
        self.groove_tree.column("name", width=220)
        self.groove_tree.grid(row=0, column=0, sticky="nsew")
        self.groove_tree.bind("<Double-1>", lambda _e: self.play_selected_groove())

        scroll = ttk.Scrollbar(body, orient="vertical", command=self.groove_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.groove_tree.configure(yscrollcommand=scroll.set)

        self.groove_status = tk.StringVar(value="No grooves loaded")
        ttk.Label(parent, textvariable=self.groove_status, foreground=THEME["muted"]).pack(anchor="w", padx=6, pady=4)

    def _build_mixer(self) -> None:
        mixer_frame = tk.Frame(self, bg=THEME["mixer_bg"], height=130)
        mixer_frame.pack(fill="x", side="bottom")
        mixer_frame.pack_propagate(False)

        ttk.Label(mixer_frame, text=" MIXER ", background=THEME["mixer_bg"], foreground=THEME["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8, pady=(6, 0))

        self.mixer_strip = tk.Frame(mixer_frame, bg=THEME["mixer_bg"])
        self.mixer_strip.pack(fill="both", expand=True, padx=8, pady=4)

        master_frame = tk.Frame(self.mixer_strip, bg=THEME["mixer_bg"], width=56)
        master_frame.pack(side="right", fill="y", padx=(8, 0))
        ttk.Label(master_frame, text="MASTER", background=THEME["mixer_bg"], foreground=THEME["muted"], font=("Segoe UI", 7)).pack()
        self.master_var = tk.DoubleVar(value=100)
        master_scale = tk.Scale(
            master_frame, from_=0, to=150, orient="vertical", variable=self.master_var,
            command=self._on_master_change, bg=THEME["mixer_bg"], fg=THEME["text"],
            troughcolor=THEME["fader_trough"], highlightthickness=0, showvalue=False, length=72,
        )
        master_scale.pack(pady=2)

        self.channels_frame = tk.Frame(self.mixer_strip, bg=THEME["mixer_bg"])
        self.channels_frame.pack(side="left", fill="both", expand=True)

    def _rebuild_mixer_channels(self) -> None:
        for w in self.channels_frame.winfo_children():
            w.destroy()
        self.fader_vars.clear()

        for ch in self.mixer_channels:
            if ch.name == "dummy":
                continue
            col = tk.Frame(self.channels_frame, bg=THEME["mixer_bg"], padx=4)
            col.pack(side="left", fill="y")
            tk.Label(col, text=ch.label, bg=THEME["mixer_bg"], fg=THEME["muted"], font=("Segoe UI", 7)).pack()
            var = tk.DoubleVar(value=ch.volume * 100)
            self.fader_vars[ch.name] = var
            scale = tk.Scale(
                col, from_=0, to=200, orient="vertical", variable=var,
                command=lambda _v, name=ch.name: self._on_fader_change(name),
                bg=THEME["mixer_bg"], fg=THEME["text"], troughcolor=THEME["fader_trough"],
                highlightthickness=0, showvalue=False, length=72, width=14,
            )
            scale.pack(pady=2)

    def _on_fader_change(self, channel: str) -> None:
        var = self.fader_vars.get(channel)
        if var:
            self.engine.set_channel_volume(channel, var.get() / 100.0)

    def _on_master_change(self, _value) -> None:
        self.engine.set_master_volume(self.master_var.get() / 100.0)

    def _bind_keys(self) -> None:
        for key, (pad, vel) in KEY_BINDINGS.items():
            self.bind(key, lambda e, p=pad, v=vel: self.hit_pad(p, v))
        self.bind("<space>", lambda e: self.hit_pad("kickR", 115))

    def bootstrap(self) -> None:
        self.rescan()

    def rescan(self) -> None:
        self.detected = detect_all()
        labels = [f"{d.name}  ({d.wav_count:,} samples)" for d in self.detected]
        self.library_combo["values"] = labels
        if labels:
            self.library_combo.current(0)
            self.on_library_change()
        else:
            self.status_var.set("No libraries found")

    def on_library_change(self) -> None:
        idx = self.library_combo.current()
        if idx < 0 or idx >= len(self.detected):
            return
        detected = self.detected[idx]
        self.current_detected = detected
        self.current_lib = detected.path
        self.midi_root = detected.midi_root

        if detected.library_type == "cakewalk_sfz":
            kits = list_drum_replacer_kits(detected.path)
        else:
            kits = list_drumsets(detected.path)
        if not kits:
            kits = [detected.name]
        self.kit_combo["values"] = kits
        self.kit_combo.current(0)

        channels, presets = load_mixer(detected.path)
        self.mixer_channels = channels
        self.mixer_presets = presets
        self.preset_combo["values"] = list(presets.keys())
        if presets:
            self.preset_var.set(list(presets.keys())[0])
        self._rebuild_mixer_channels()
        self.apply_mix_preset()
        self.load_selected_kit()

        if self.midi_root:
            count = self.groove_library.scan(self.midi_root)
            self.groove_status.set(f"{count:,} grooves")
            self.refresh_groove_list()

    def load_selected_kit(self) -> None:
        if not self.current_lib:
            return
        kit_name = self.kit_var.get()
        try:
            if self.current_detected and self.current_detected.library_type == "cakewalk_sfz":
                kit = load_drum_replacer_kit(self.current_lib, kit_name)
            else:
                kits = list_drumsets(self.current_lib)
                kit = load_kit(self.current_lib, kit_name if kit_name in kits else None)

            self.engine.load_kit(kit)
            visual = load_kit_visual(self.current_lib)
            self.kit_canvas.load_visual(visual)
            self.status_var.set(f"{kit.name}  •  {self.engine.pad_count()} pads  •  {self.engine.sample_count():,} samples")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Failed to load kit:\n{exc}")

    def apply_mix_preset(self) -> None:
        preset_name = self.preset_var.get()
        preset = self.mixer_presets.get(preset_name)
        if not preset:
            return
        for ch_name, ch in preset.channels.items():
            if ch_name in self.fader_vars:
                self.fader_vars[ch_name].set(ch.volume * 100)
                self.engine.set_channel_volume(ch_name, ch.volume)

    def hit_pad(self, pad_name: str, velocity: int = 100) -> bool:
        targets = [pad_name] + PAD_ALIASES_ENGINE.get(pad_name, [])
        for target in targets:
            if self.engine.trigger_pad(target, velocity):
                return True
        return False

    def refresh_groove_list(self) -> None:
        self.groove_tree.delete(*self.groove_tree.get_children())
        for groove in self.groove_library.filter(self.groove_search.get()):
            self.groove_tree.insert("", "end", iid=str(groove.path), values=(groove.genre, groove.bpm, groove.name))

    def play_selected_groove(self) -> None:
        sel = self.groove_tree.selection()
        if not sel:
            return
        path = Path(sel[0])
        self.groove_player.play_file(path)
        self.groove_status.set(f"Playing: {path.stem}")

    def _show_about(self) -> None:
        import sys

        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).resolve().parent.parent
        license_path = base / "LICENSE"
        if not license_path.exists():
            license_path = Path(__file__).resolve().parent.parent / "LICENSE"
        license_note = "See LICENSE file in the install folder."
        if license_path.exists():
            license_note = license_path.read_text(encoding="utf-8")[:1200]

        win = tk.Toplevel(self)
        win.title(f"About {APP_NAME}")
        win.geometry("480x380")
        win.configure(bg=THEME["panel"])
        win.resizable(False, False)

        ttk.Label(win, text=APP_NAME, font=("Segoe UI", 16, "bold"), background=THEME["panel"]).pack(pady=(16, 4))
        ttk.Label(win, text=f"Version {APP_VERSION}", background=THEME["panel"], foreground=THEME["muted"]).pack()
        ttk.Label(
            win,
            text="Free & open source (MIT License)\nFree for everyone to use, modify, and share.",
            background=THEME["panel"],
            justify="center",
        ).pack(pady=(8, 12))

        text = tk.Text(win, height=12, bg=THEME["panel2"], fg=THEME["text"], wrap="word", relief="flat", font=("Segoe UI", 9))
        text.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        body = (
            f"{APP_NAME} is open-source application software.\n\n"
            "It does not include or redistribute any drum sample libraries.\n"
            "Use only with content you legally own.\n\n"
            f"Copyright (c) 2026 {PUBLISHER}\n"
            f"License: {LICENSE_NAME}\n\n"
            f"{license_note}"
        )
        text.insert("1.0", body)
        text.configure(state="disabled")

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(btns, text="License (web)", command=lambda: webbrowser.open(LICENSE_URL)).pack(side="left")
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")

    def _show_sources_dialog(self) -> None:
        win = tk.Toplevel(self)
        win.title("Sample Sources")
        win.geometry("520x420")
        win.configure(bg=THEME["panel"])
        text = tk.Text(win, bg=THEME["panel2"], fg=THEME["text"], wrap="word", relief="flat")
        text.pack(fill="both", expand=True, padx=12, pady=12)
        catalog = load_catalog()
        lines = [f"{PUBLISHER} — libraries on this PC\n"]
        for d in self.detected:
            lines.append(f"• {d.name}: {d.wav_count:,} samples, {d.midi_count:,} MIDI")
        lines.append("\nSupported vendors:")
        for s in catalog.get("sources", []):
            lines.append(f"  {s.get('name')} ({s.get('vendor')})")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btns, text="Add Library Folder", command=lambda: (self.add_library_folder(), win.destroy())).pack(side="right")
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right", padx=(0, 8))

    def add_library_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Select drum library folder")
        if not chosen:
            return
        from library_scanner import DetectedLibrary, _count_wavs, _find_midi_root

        path = Path(chosen)
        midi_root = _find_midi_root(path) or _find_midi_root(path.parent)
        self.detected.append(
            DetectedLibrary(
                path=path, name=path.name, source_id="custom",
                wav_count=_count_wavs(path), midi_root=midi_root,
                midi_count=len(list(midi_root.rglob("*.mid"))) if midi_root else 0,
            )
        )
        self.rescan()


def main() -> None:
    app = DrummerStudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
