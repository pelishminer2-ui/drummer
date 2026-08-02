#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Drummer Studio Contributors
"""Drummer Studio — free open-source drum kit player, mixer, and groove browser."""

from __future__ import annotations

import threading
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import COPY, DND_FILES, TkinterDnD

    _TkBase = TkinterDnD.Tk
    _DND_AVAILABLE = True
except ImportError:
    _TkBase = tk.Tk
    _DND_AVAILABLE = False
    COPY = DND_FILES = None  # type: ignore[misc, assignment]

from audacity_launch import open_in_audacity
from file_drag import format_dnd_files

from kit_ui import (
    PAD_ALIASES_ENGINE,
    PIECE_HIT_PRIORITY,
    PIECE_TO_PADS,
    KitRegion,
    KitVisual,
    load_kit_visual,
    load_mixer,
)
from audio_analyze import analyze_file, record_guitar
from audio_loops import AudioLoopLibrary, AudioLoopPlayer
from folder_kit_parser import list_folder_kits, load_folder_kit
from gpu_backend import get_gpu_info
from groove_catalog import load_session_grooves, scan_all_grooves
from demo_catalog import DemoLibrary, DemoPlayer
from groove_visual import PIECE_ALIASES, extract_groove_visual_hits
from groove_export import render_midi_to_wav
from groove_matcher import GrooveMatch, find_matches
from playback_kit import load_groove_playback_kit, load_playback_kit, needs_playback_fallback
from library_parser import list_drumsets, load_kit, resolve_kit_name
from library_scanner import DetectedLibrary, add_custom_library, detect_all, libraries_root, load_manifest
from midi_drum_map import classify_groove_midi
from stream_loop_catalog import STREAM_LOOP_TYPES, StreamLoopLibrary
from midi_grooves import GrooveLibrary, GroovePlayer
from selected_tracks import SelectedTrack, tracks_for_library
from sampler_engine import SamplerEngine
from sfz_parser import list_sfz_kits, load_sfz_kit

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

APP_NAME = "Drummer Studio"
APP_VERSION = "2.6.14"
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
    """Clickable drum kit photo (main studio view)."""

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
        lx = (event.x - self._offset_x) / max(self._scale, 0.001)
        ly = (event.y - self._offset_y) / max(self._scale, 0.001)
        hits = [
            region
            for region in self.visual.regions
            if region.x <= lx <= region.x + region.width and region.y <= ly <= region.y + region.height
        ]
        if not hits:
            return
        region = min(
            hits,
            key=lambda r: PIECE_HIT_PRIORITY.index(r.piece) if r.piece in PIECE_HIT_PRIORITY else 99,
        )
        self._flash(region)
        self.on_hit(region.piece, 105)

    def flash_piece(self, piece: str) -> None:
        if not self.visual:
            return
        targets = {piece, PIECE_ALIASES.get(piece, piece)}
        for region in self.visual.regions:
            if region.piece in targets:
                self._flash(region)
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


class DrummerStudioApp(_TkBase):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1280x780")
        self.minsize(1024, 680)
        self.configure(bg=THEME["bg"])

        self.engine = SamplerEngine()
        self.groove_library = GrooveLibrary()
        self.audio_loop_library = AudioLoopLibrary()
        self.groove_player = GroovePlayer()
        self.audio_loop_player = AudioLoopPlayer()
        self.demo_library = DemoLibrary()
        self.stream_loop_library = StreamLoopLibrary()
        self.demo_player = DemoPlayer()
        self._demo_items: list[tuple[str, Path]] = []
        self._groove_items: list[tuple[str, Path]] = []
        self._pinned_tracks: list[SelectedTrack] = []
        self._match_mode = False
        self._match_searching = False
        self._last_analysis = None
        self._last_matches: list[GrooveMatch] = []
        self._last_recording_path: Path | None = None
        self._open_in_audacity_after_record = tk.BooleanVar(value=True)
        self._groove_visual_after_ids: list[str] = []
        self._analyzing_guitar = False
        self._recording_guitar = False
        self._record_seconds = tk.IntVar(value=8)
        self.detected: list[DetectedLibrary] = detect_all()
        self.current_detected = self.detected[0] if self.detected else None
        self.current_lib = self.detected[0].path if self.detected else None
        self.midi_root = self.detected[0].midi_root if self.detected else None
        self.mixer_channels: list = []
        self.mixer_presets: dict = {}
        self.fader_vars: dict[str, tk.DoubleVar] = {}
        self._piece_click_index: dict[str, int] = {}
        self._playback_kit_label = ""
        self._groove_kit = None
        self._groove_kit_label = ""

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
        self.preset_combo.pack(side="left", padx=(6, 4))
        self.preset_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_mix_preset())
        ttk.Button(toolbar, text="Apply Mix", command=self.apply_mix_preset).pack(side="left", padx=(0, 12))

        ttk.Button(toolbar, text="Rescan Libraries", command=self.rescan).pack(side="right", padx=4)
        ttk.Button(toolbar, text="About", command=self._show_about).pack(side="right", padx=4)
        ttk.Button(toolbar, text="Libraries", command=self._show_libraries_dialog).pack(side="right")

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(toolbar, textvariable=self.status_var, style="Toolbar.TLabel").pack(side="right", padx=(0, 16))

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        kit_panel = ttk.Frame(main, style="Toolbar.TFrame")
        grooves_panel = ttk.Frame(main)
        main.add(kit_panel, weight=3)
        main.add(grooves_panel, weight=2)

        ttk.Label(kit_panel, text="DRUM KIT", style="Toolbar.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(6, 0))
        self.kit_canvas = KitCanvas(kit_panel, on_hit=self.hit_piece, bg=THEME["panel2"], bd=0)
        self.kit_canvas.pack(fill="both", expand=True, padx=6, pady=6)

        hint = ttk.Label(kit_panel, text="Click drums on the kit  •  Space kick  F snare  G/H hats  1/2/3 toms  J ride", style="Toolbar.TLabel")
        hint.pack(anchor="w", padx=10, pady=(0, 6))

        self._build_groove_panel(grooves_panel)
        self._build_mixer()

    def _build_groove_panel(self, parent) -> None:
        match_frame = ttk.LabelFrame(
            parent,
            text="Match — record or import a track, then find matching grooves (BPM + rhythm + key + AI feel)",
            padding=(6, 4),
        )
        match_frame.pack(fill="x", padx=4, pady=(6, 4))

        match_row = ttk.Frame(match_frame)
        match_row.pack(fill="x")
        ttk.Button(match_row, text="Record Guitar", command=self._record_guitar).pack(side="left", padx=(0, 4))
        ttk.Label(match_row, text="sec").pack(side="left")
        ttk.Spinbox(match_row, from_=4, to=30, width=4, textvariable=self._record_seconds).pack(side="left", padx=(0, 8))
        ttk.Button(match_row, text="Import Track", command=self._import_track).pack(side="left", padx=(0, 4))
        ttk.Button(match_row, text="Match Selected", command=self._match_selected_track).pack(side="left", padx=(0, 4))
        ttk.Button(match_row, text="Find Matches", command=self._find_groove_matches).pack(side="left", padx=(0, 4))
        ttk.Button(match_row, text="Show All", command=self._clear_match_mode).pack(side="left")

        audacity_row = ttk.Frame(match_frame)
        audacity_row.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(
            audacity_row,
            text="Open in Audacity after record",
            variable=self._open_in_audacity_after_record,
        ).pack(side="left")
        ttk.Button(audacity_row, text="Open in Audacity", command=self._open_last_in_audacity).pack(
            side="left", padx=(8, 0)
        )

        self.match_status = tk.StringVar(value=self._match_idle_status())
        ttk.Label(match_frame, textvariable=self.match_status, foreground=THEME["muted"], wraplength=420).pack(anchor="w", pady=(4, 0))

        browser = ttk.Notebook(parent)
        browser.pack(fill="both", expand=True, padx=2, pady=(4, 0))
        grooves_tab = ttk.Frame(browser)
        demos_tab = ttk.Frame(browser)
        selected_tab = ttk.Frame(browser)
        matches_tab = ttk.Frame(browser)
        browser.add(grooves_tab, text="Grooves")
        browser.add(demos_tab, text="Ass Kickers")
        browser.add(selected_tab, text="Selected Tracks")
        browser.add(matches_tab, text="Matches Found")
        self._build_grooves_tab(grooves_tab)
        self._build_demo_panel(demos_tab)
        self._build_selected_tracks_tab(selected_tab)
        self._build_matches_found_tab(matches_tab)
        self.browser_notebook = browser
        self._matches_tab = matches_tab

    def _build_grooves_tab(self, parent) -> None:
        ttk.Label(parent, text="GROOVE BROWSER", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=(6, 4))
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=(0, 4))
        self.groove_search = tk.StringVar()
        self.groove_search.trace_add("write", lambda *_: self.refresh_groove_list())
        ttk.Entry(top, textvariable=self.groove_search).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Play", command=self.play_selected_groove).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Stop", command=self._stop_groove).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Add to Selected", command=self._pin_from_grooves).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Export WAV", command=self._export_groove_wav).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Open File", command=self._open_groove_file).pack(side="right", padx=(4, 0))

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, padx=4, pady=4)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.groove_tree = ttk.Treeview(
            body, columns=("genre", "bpm", "score", "rhythm", "name"), show="headings", selectmode="browse"
        )
        self.groove_tree.heading("genre", text="Genre")
        self.groove_tree.heading("bpm", text="BPM")
        self.groove_tree.heading("score", text="Match")
        self.groove_tree.heading("rhythm", text="Feel")
        self.groove_tree.heading("name", text="Groove")
        self.groove_tree.column("genre", width=80)
        self.groove_tree.column("bpm", width=55)
        self.groove_tree.column("score", width=45)
        self.groove_tree.column("rhythm", width=45)
        self.groove_tree.column("name", width=160)
        self.groove_tree.grid(row=0, column=0, sticky="nsew")
        self.groove_tree.bind("<Double-1>", lambda _e: self.play_selected_groove())

        scroll = ttk.Scrollbar(body, orient="vertical", command=self.groove_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.groove_tree.configure(yscrollcommand=scroll.set)

        self.groove_status = tk.StringVar(value="No grooves loaded")
        ttk.Label(parent, textvariable=self.groove_status, foreground=THEME["muted"]).pack(anchor="w", padx=6, pady=4)

    def _build_demo_panel(self, parent) -> None:
        ttk.Label(parent, text="ASS KICKERS", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=(6, 4))
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=(0, 4))
        self.demo_section_var = tk.StringVar(value="All")
        self.demo_section_combo = ttk.Combobox(top, textvariable=self.demo_section_var, width=28, state="readonly")
        self.demo_section_combo.pack(side="left", padx=(0, 6))
        self.demo_section_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_demo_list())
        ttk.Label(top, text="Genre").pack(side="left", padx=(0, 4))
        self.demo_genre_var = tk.StringVar(value="All")
        self.demo_genre_combo = ttk.Combobox(top, textvariable=self.demo_genre_var, width=12, state="readonly")
        self.demo_genre_combo.pack(side="left", padx=(0, 6))
        self.demo_genre_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_demo_list())
        self.demo_search = tk.StringVar()
        self.demo_search.trace_add("write", lambda *_: self.refresh_demo_list())
        ttk.Entry(top, textvariable=self.demo_search).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Play", command=self.play_selected_demo).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Stop", command=self._stop_all_playback).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Add to Selected", command=self._pin_from_demos).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Export WAV", command=self._export_demo).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Open File", command=self._open_demo_file).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Refresh", command=self._import_ssd_demos).pack(side="right", padx=(4, 0))

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, padx=4, pady=4)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.demo_tree = ttk.Treeview(
            body, columns=("genre", "section", "subtitle", "title"), show="headings", selectmode="browse"
        )
        self.demo_tree.heading("genre", text="Genre")
        self.demo_tree.heading("section", text="Section")
        self.demo_tree.heading("subtitle", text="Description")
        self.demo_tree.heading("title", text="Track")
        self.demo_tree.column("genre", width=70)
        self.demo_tree.column("section", width=120)
        self.demo_tree.column("subtitle", width=160)
        self.demo_tree.column("title", width=130)
        self.demo_tree.grid(row=0, column=0, sticky="nsew")
        self.demo_tree.bind("<Double-1>", lambda _e: self.play_selected_demo())

        scroll = ttk.Scrollbar(body, orient="vertical", command=self.demo_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.demo_tree.configure(yscrollcommand=scroll.set)

        self.demo_status = tk.StringVar(value="Run Import-SSD-Demos.ps1 to fetch Ass Kickers")
        ttk.Label(parent, textvariable=self.demo_status, foreground=THEME["muted"], wraplength=420).pack(
            anchor="w", padx=6, pady=4
        )

    def _build_selected_tracks_tab(self, parent) -> None:
        ttk.Label(parent, text="SELECTED TRACKS", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=(6, 2))
        self.selected_context = tk.StringVar(value="Choose a library and kit above")
        ttk.Label(parent, textvariable=self.selected_context, foreground=THEME["muted"], wraplength=420).pack(
            anchor="w", padx=6, pady=(0, 4)
        )

        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=(0, 4))
        self.selected_search = tk.StringVar()
        self.selected_search.trace_add("write", lambda *_: self.refresh_selected_tracks())
        ttk.Entry(top, textvariable=self.selected_search).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Play", command=self.play_selected_track).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Stop", command=self._stop_all_playback).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Remove", command=self._remove_pinned_track).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Export WAV", command=self._export_selected_track).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Open File", command=self._open_selected_track).pack(side="right", padx=(4, 0))

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, padx=4, pady=4)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.selected_tree = ttk.Treeview(
            body, columns=("kind", "genre", "bpm", "name", "source"), show="headings", selectmode="browse"
        )
        self.selected_tree.heading("kind", text="Type")
        self.selected_tree.heading("genre", text="Genre")
        self.selected_tree.heading("bpm", text="BPM")
        self.selected_tree.heading("name", text="Track")
        self.selected_tree.heading("source", text="Source")
        self.selected_tree.column("kind", width=48)
        self.selected_tree.column("genre", width=72)
        self.selected_tree.column("bpm", width=52)
        self.selected_tree.column("name", width=140)
        self.selected_tree.column("source", width=120)
        self.selected_tree.grid(row=0, column=0, sticky="nsew")
        self.selected_tree.bind("<Double-1>", lambda _e: self.play_selected_track())

        scroll = ttk.Scrollbar(body, orient="vertical", command=self.selected_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.selected_tree.configure(yscrollcommand=scroll.set)

        self.selected_status = tk.StringVar(value="Updates when you change Library or Kit")
        ttk.Label(parent, textvariable=self.selected_status, foreground=THEME["muted"], wraplength=420).pack(
            anchor="w", padx=6, pady=4
        )

    def _build_matches_found_tab(self, parent) -> None:
        ttk.Label(parent, text="MATCHES FOUND", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=4, pady=(6, 2))
        self.matches_context = tk.StringVar(value="Record, import, or select a track — matches appear here after Find Matches")
        ttk.Label(parent, textvariable=self.matches_context, foreground=THEME["muted"], wraplength=420).pack(
            anchor="w", padx=6, pady=(0, 4)
        )

        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(top, text="Play", command=self.play_selected_match).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Stop", command=self._stop_groove).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Add to Selected", command=self._pin_from_matches).pack(side="right", padx=(4, 0))
        ttk.Button(top, text="Open File", command=self._open_match_file).pack(side="right", padx=(4, 0))

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True, padx=4, pady=4)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.matches_tree = ttk.Treeview(
            body, columns=("genre", "bpm", "score", "rhythm", "name"), show="headings", selectmode="browse"
        )
        self.matches_tree.heading("genre", text="Genre")
        self.matches_tree.heading("bpm", text="BPM")
        self.matches_tree.heading("score", text="Match")
        self.matches_tree.heading("rhythm", text="Feel")
        self.matches_tree.heading("name", text="Groove")
        self.matches_tree.column("genre", width=80)
        self.matches_tree.column("bpm", width=55)
        self.matches_tree.column("score", width=45)
        self.matches_tree.column("rhythm", width=45)
        self.matches_tree.column("name", width=160)
        self.matches_tree.grid(row=0, column=0, sticky="nsew")
        self.matches_tree.bind("<Double-1>", lambda _e: self.play_selected_match())
        if _DND_AVAILABLE:
            self.matches_tree.drag_source_register(1, DND_FILES)
            self.matches_tree.dnd_bind("<<DragInitCmd>>", self._match_drag_init)

        scroll = ttk.Scrollbar(body, orient="vertical", command=self.matches_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.matches_tree.configure(yscrollcommand=scroll.set)

        self.matches_status = tk.StringVar(value="No matches yet — drag a match into your DAW")
        ttk.Label(parent, textvariable=self.matches_status, foreground=THEME["muted"], wraplength=420).pack(
            anchor="w", padx=6, pady=4
        )

    def _update_matches_tab_label(self, count: int | None = None) -> None:
        if not hasattr(self, "_matches_tab"):
            return
        label = "Matches Found" if count is None else f"Matches Found ({count})"
        self.browser_notebook.tab(self._matches_tab, text=label)

    def _refresh_matches_tab(self, matches: list[GrooveMatch]) -> None:
        if not hasattr(self, "matches_tree"):
            return
        self._last_matches = matches
        self.matches_tree.delete(*self.matches_tree.get_children())
        seen_iids: set[str] = set()
        for m in matches:
            iid = f"{m.kind}:{m.path.resolve()}"
            if iid in seen_iids:
                continue
            seen_iids.add(iid)
            self.matches_tree.insert(
                "",
                "end",
                iid=iid,
                values=(m.genre[:20], m.bpm_label, f"{m.score:.0f}", f"{m.rhythm_score:.0%}", m.name),
            )
        if self._last_analysis:
            a = self._last_analysis
            self.matches_context.set(
                f"Your take: ~{a.bpm} BPM  •  Key {a.key_root} {a.key_mode}  •  {a.duration_sec:.1f}s"
            )
        if matches:
            top = matches[0]
            self.matches_status.set(
                f"{len(matches)} matches  •  Best: {top.name} ({top.score:.0f}%)  •  drag into your DAW"
            )
        else:
            self.matches_status.set("No matches found — try a longer recording or different tempo")

    def _resolve_match_drag_path(self, iid: str) -> Path | None:
        if iid.startswith("wav:"):
            path = Path(iid[4:])
            return path if path.exists() else None
        if not iid.startswith("mid:"):
            return None
        midi = Path(iid[4:])
        if not midi.exists():
            return None
        cache_dir = libraries_root() / "User-Exports" / "Drag-Cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        out = cache_dir / f"{midi.stem}.wav"
        if out.exists() and out.stat().st_mtime >= midi.stat().st_mtime:
            return out
        try:
            kit, _, _ = load_groove_playback_kit(self.detected)
            render_midi_to_wav(midi, kit, out)
            return out
        except (OSError, RuntimeError, ValueError):
            return midi

    def _match_drag_init(self, event) -> tuple:
        if not _DND_AVAILABLE:
            return (COPY, DND_FILES, "")
        row = self.matches_tree.identify_row(event.y)
        if row:
            self.matches_tree.selection_set(row)
            self.matches_tree.focus(row)
        sel = self.matches_tree.selection()
        if not sel:
            return (COPY, DND_FILES, "")
        path = self._resolve_match_drag_path(sel[0])
        if not path or not path.exists():
            return (COPY, DND_FILES, "")
        self.matches_status.set(f"Dragging: {path.name}")
        return (COPY, DND_FILES, format_dnd_files([path]))

    def play_selected_match(self) -> None:
        sel = self.matches_tree.selection()
        if not sel:
            return
        iid = sel[0]
        self._stop_all_playback()
        if iid.startswith("wav:"):
            self._play_audio_loop(Path(iid[4:]), self.matches_status)
        elif iid.startswith("mid:"):
            self._play_midi_groove(Path(iid[4:]), self.matches_status)

    def _pin_from_matches(self) -> None:
        sel = self.matches_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a match in the list first.")
            return
        iid = sel[0]
        match = next((m for m in self._last_matches if f"{m.kind}:{m.path.resolve()}" == iid), None)
        if match:
            kind = "midi" if match.kind == "mid" else match.kind
            self._pin_track(
                SelectedTrack(
                    path=match.path,
                    name=match.name,
                    kind=kind,
                    genre=match.genre,
                    bpm=match.bpm_label,
                    source="Match",
                )
            )
            return
        if iid.startswith("wav:"):
            path = Path(iid[4:])
            self._pin_track(SelectedTrack(path=path, name=path.stem, kind="wav", genre="WAV", bpm="", source="Match"))
        elif iid.startswith("mid:"):
            path = Path(iid[4:])
            self._pin_track(SelectedTrack(path=path, name=path.stem, kind="midi", genre="MIDI", bpm="", source="Match"))

    def _open_match_file(self) -> None:
        sel = self.matches_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if not (iid.startswith("wav:") or iid.startswith("mid:")):
            return
        path = Path(iid[4:])
        import os
        import subprocess

        if path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            messagebox.showerror(APP_NAME, f"File not found:\n{path}")

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
        self._load_demos()

    def rescan(self) -> None:
        self.detected = detect_all()
        labels = []
        for d in self.detected:
            if d.playable_wav_count:
                labels.append(f"{d.name}  ({d.playable_wav_count:,} playable samples)")
            elif d.library_type == "pdk" and d.playable_wav_count == 0:
                labels.append(f"{d.name}  (PDK — select to extract samples)")
            elif d.library_type == "vst":
                labels.append(f"{d.name}  (VST3 plugin — use in your DAW)")
            elif d.library_type in STREAM_LOOP_TYPES:
                labels.append(f"{d.name}  ({d.wav_count:,} loops)")
            elif d.sample_format == "ttpw":
                labels.append(f"{d.name}  (Toontrack format — kit won't play here)")
            else:
                labels.append(f"{d.name}  ({d.wav_count:,} samples)")
        self.library_combo["values"] = labels
        if labels:
            self.library_combo.current(0)
            self.on_library_change()
        else:
            self.status_var.set(f"No libraries in {libraries_root()} — run Import-Libraries.ps1")

    def on_library_change(self) -> None:
        idx = self.library_combo.current()
        if idx < 0 or idx >= len(self.detected):
            return
        detected = self.detected[idx]
        self.current_detected = detected
        self.current_lib = detected.path
        self.midi_root = detected.midi_root

        if detected.library_type == "sfz":
            kits = list_sfz_kits(detected.path, detected.sfz_kits)
        elif detected.library_type == "folder":
            kits = list_folder_kits(detected.path)
        elif detected.library_type == "pdk":
            from pdk_parser import ensure_pdk_extracted, list_pdk_kits

            manifest_entry = next(
                (e for e in load_manifest().get("libraries", []) if e.get("id") == detected.library_id),
                {},
            )
            try:
                self.status_var.set(f"Extracting {detected.name} samples from .pdk ...")
                self.update_idletasks()
                ensure_pdk_extracted(detected.path, manifest_entry.get("pdk_file"))
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"Could not extract MT Wild Drums samples:\n{exc}")
            kits = list_pdk_kits(detected.path)
        else:
            kits = list_drumsets(detected.path, detected.kit_labels)
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
        self.load_selected_kit()
        self.apply_mix_preset()

        self.groove_library.grooves.clear()
        self.audio_loop_library.loops.clear()
        self._groove_items.clear()

        self.groove_status.set("Loading grooves…")
        self.update_idletasks()
        if detected.library_type in STREAM_LOOP_TYPES:
            self.groove_library.grooves.clear()
        else:
            self.groove_library.grooves = load_session_grooves(detected)
        lib_root = libraries_root()

        loops_dir = detected.path / "Loops"
        if detected.library_type in STREAM_LOOP_TYPES:
            self.stream_loop_library.load(detected.path)
            self.audio_loop_library.loops = self.stream_loop_library.to_audio_loops()
        elif loops_dir.is_dir():
            self.audio_loop_library.scan(loops_dir)
        else:
            self.audio_loop_library.loops.clear()
        if detected.library_type not in STREAM_LOOP_TYPES:
            for entry in load_manifest().get("libraries", []):
                if entry.get("id") == detected.library_id:
                    lf = entry.get("loops_folder")
                    if lf:
                        lp = lib_root / lf
                        if lp.is_dir() and lp != loops_dir:
                            self.audio_loop_library.scan(lp)

        midi_count = len(self.groove_library.grooves)
        loop_count = len(self.audio_loop_library.loops)
        if detected.library_type in STREAM_LOOP_TYPES:
            groove_note = f"{loop_count:,} {detected.name} loops"
        elif detected.midi_count == 0 and midi_count:
            groove_note = f"{midi_count:,} shared MIDI grooves"
        elif detected.midi_count:
            groove_note = f"{midi_count:,} MIDI"
        else:
            groove_note = "No MIDI grooves — run Import-Libraries.ps1"
        self.groove_status.set(f"{groove_note}  •  {loop_count:,} audio loops")
        self.refresh_groove_list()
        self.refresh_selected_tracks()

    def _ensure_groove_kit(self) -> bool:
        """Load Pack Punk (or next best) for smooth Toontrack MIDI groove preview."""
        try:
            kit, lib_name, kit_name = load_groove_playback_kit(self.detected)
            self._groove_kit = kit
            self._groove_kit_label = f"{kit_name} ({lib_name})"
            return True
        except RuntimeError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return False

    def _ensure_playback_ready(self) -> bool:
        if self.engine.kit and self.engine.sample_count() > 0:
            return True
        try:
            kit, lib_name, kit_name = load_playback_kit(self.detected)
            self.engine.load_kit(kit)
            self._playback_kit_label = f"{kit_name} ({lib_name})"
            return True
        except RuntimeError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return False

    def load_selected_kit(self) -> None:
        if not self.current_lib:
            return
        kit_name = self.kit_var.get()
        labels = self.current_detected.kit_labels if self.current_detected else {}
        visual = load_kit_visual(self.current_lib)

        if self.current_detected and self.current_detected.library_type in STREAM_LOOP_TYPES:
            manifest_entry = next(
                (e for e in load_manifest().get("libraries", []) if e.get("id") == self.current_detected.library_id),
                {},
            )
            playback_from = manifest_entry.get("playback_from", "Pack-Punk")
            pack_path = libraries_root() / playback_from
            self.kit_canvas.load_visual(load_kit_visual(pack_path))
            kits = list_folder_kits(pack_path) if pack_path.is_dir() else ["Loops"]
            kit_name = kits[0] if kits else "Loops"
            kit = load_folder_kit(pack_path, kit_name)
            self.engine.load_kit(kit)
            self._groove_kit = kit
            self._playback_kit_label = f"{kit_name} (Pack Punk)"
            self._groove_kit_label = self._playback_kit_label
            loop_n = len(self.stream_loop_library.tracks)
            lib_name = self.current_detected.name if self.current_detected else "Loops"
            self.status_var.set(f"{lib_name}  •  {loop_n} SoundCloud loops  •  kit: {kit_name}")
            self.refresh_selected_tracks()
            return

        self.kit_canvas.load_visual(visual)

        if self.current_detected and self.current_detected.library_type == "pdk":
            from pdk_parser import load_pdk_kit

            manifest_entry = next(
                (e for e in load_manifest().get("libraries", []) if e.get("id") == self.current_detected.library_id),
                {},
            )
            kit = load_pdk_kit(self.current_lib, kit_name, manifest_entry.get("pdk_file"))
            self.engine.load_kit(kit)
            self._playback_kit_label = kit_name
            self.status_var.set(
                f"{kit_name}  •  {self.engine.pad_count()} pads  •  {self.engine.sample_count():,} MT Power Drum Kit samples"
            )
            self.refresh_selected_tracks()
            return

        if needs_playback_fallback(self.current_detected):
            try:
                kit, lib_name, playback_name = load_groove_playback_kit(self.detected)
                self.engine.load_kit(kit)
                self._groove_kit = kit
                self._playback_kit_label = f"{playback_name} ({lib_name})"
                self._groove_kit_label = self._playback_kit_label
                lib_label = self.current_detected.name if self.current_detected else "Library"
                self.status_var.set(
                    f"{lib_label}  •  MIDI grooves  •  sounds: {self._playback_kit_label}"
                )
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"Could not load playback kit:\n{exc}")
            self.refresh_selected_tracks()
            return

        try:
            if self.current_detected and self.current_detected.library_type == "sfz":
                kit = load_sfz_kit(self.current_lib, kit_name, self.current_detected.sfz_kits)
            elif self.current_detected and self.current_detected.library_type in ("folder", "cool_imports"):
                kit = load_folder_kit(self.current_lib, kit_name)
            else:
                internal_name = resolve_kit_name(kit_name, labels)
                kit = load_kit(self.current_lib, internal_name)

            self.engine.load_kit(kit)
            if self.engine.sample_count() == 0:
                kit, lib_name, playback_name = load_playback_kit(self.detected)
                self.engine.load_kit(kit)
                self._playback_kit_label = f"{playback_name} ({lib_name})"
                self.status_var.set(
                    f"{kit_name}  •  MIDI via {self._playback_kit_label}"
                )
            else:
                self._playback_kit_label = kit_name
                self.status_var.set(
                    f"{kit_name}  •  {self.engine.pad_count()} pads  •  {self.engine.sample_count():,} samples loaded"
                )
        except Exception as exc:
            if self._ensure_playback_ready():
                self.status_var.set(f"MIDI playback  •  sounds: {self._playback_kit_label}")
            else:
                messagebox.showerror(APP_NAME, f"Failed to load kit:\n{exc}")

        self.refresh_selected_tracks()

    def refresh_selected_tracks(self) -> None:
        if not hasattr(self, "selected_tree"):
            return
        lib = self.current_detected
        kit = self.kit_var.get() if hasattr(self, "kit_var") else ""
        if lib:
            self.selected_context.set(f"{lib.name}  •  {kit}")
        else:
            self.selected_context.set("Choose a library and kit above")

        library_list = tracks_for_library(lib, kit)
        pinned_keys = {t.iid for t in self._pinned_tracks}
        q = self.selected_search.get().strip().lower() if hasattr(self, "selected_search") else ""

        combined: list[SelectedTrack] = list(self._pinned_tracks)
        for track in library_list:
            if track.iid not in pinned_keys:
                combined.append(track)

        if q:
            combined = [
                t
                for t in combined
                if q in t.name.lower()
                or q in t.genre.lower()
                or q in t.bpm.lower()
                or q in t.source.lower()
                or q in t.kind.lower()
            ]

        self.selected_tree.delete(*self.selected_tree.get_children())
        for track in combined:
            kind_label = {"midi": "MIDI", "wav": "WAV", "demo": "Demo"}.get(track.kind, track.kind.upper())
            self.selected_tree.insert(
                "",
                "end",
                iid=track.iid,
                values=(kind_label, track.genre, track.bpm, track.name, track.source),
            )

        pinned = len(self._pinned_tracks)
        lib_count = len(library_list)
        self.selected_status.set(f"{lib_count:,} for this library  •  {pinned} pinned  •  {len(combined):,} shown")

    def _track_from_tree_iid(self, iid: str) -> SelectedTrack | None:
        if ":" not in iid:
            return None
        kind, _, raw = iid.partition(":")
        path = Path(raw)
        for track in self._pinned_tracks:
            if track.iid == iid:
                return track
        lib = self.current_detected
        kit = self.kit_var.get()
        for track in tracks_for_library(lib, kit):
            if track.iid == iid:
                return track
        if path.exists():
            return SelectedTrack(path=path, name=path.stem, kind=kind, genre="", bpm="", source="")
        return None

    def _pin_track(self, track: SelectedTrack) -> None:
        if any(t.iid == track.iid for t in self._pinned_tracks):
            self.selected_status.set(f"Already in Selected Tracks: {track.name}")
            return
        pinned = SelectedTrack(
            path=track.path,
            name=track.name,
            kind=track.kind,
            genre=track.genre,
            bpm=track.bpm,
            source="Pinned",
        )
        self._pinned_tracks.insert(0, pinned)
        self.refresh_selected_tracks()
        if hasattr(self, "browser_notebook"):
            self.browser_notebook.select(2)
        self.selected_status.set(f"Added: {track.name}")

    def _pin_from_grooves(self) -> None:
        sel = self.groove_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a groove in the Grooves list first.")
            return
        iid = sel[0]
        if iid.startswith("wav:"):
            path = Path(iid[4:])
            loop = next((l for l in self.audio_loop_library.loops if l.path.resolve() == path.resolve()), None)
            if loop:
                self._pin_track(
                    SelectedTrack(path=loop.path, name=loop.name, kind="wav", genre=loop.genre, bpm=loop.bpm, source="Pinned")
                )
            else:
                self._pin_track(SelectedTrack(path=path, name=path.stem, kind="wav", genre="WAV", bpm="", source="Pinned"))
        elif iid.startswith("mid:"):
            path = Path(iid[4:])
            groove = next((g for g in self.groove_library.grooves if g.path.resolve() == path.resolve()), None)
            if groove:
                self._pin_track(
                    SelectedTrack(
                        path=groove.path,
                        name=groove.name,
                        kind="midi",
                        genre=groove.genre or "MIDI",
                        bpm=groove.bpm,
                        source="Pinned",
                    )
                )
            else:
                self._pin_track(SelectedTrack(path=path, name=path.stem, kind="midi", genre="MIDI", bpm="", source="Pinned"))
        elif ":" in iid:
            kind, _, raw = iid.partition(":")
            path = Path(raw)
            self._pin_track(SelectedTrack(path=path, name=path.stem, kind=kind, genre="", bpm="", source="Pinned"))

    def _pin_from_demos(self) -> None:
        sel = self.demo_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a track in Ass Kickers first.")
            return
        iid = sel[0]
        if not iid.startswith("demo:"):
            return
        path = Path(iid[5:])
        track = next((t for t in self.demo_library.tracks if t.path.resolve() == path.resolve()), None)
        if track:
            self._pin_track(
                SelectedTrack(
                    path=track.path,
                    name=track.title,
                    kind="demo",
                    genre=track.genre,
                    bpm="",
                    source="Pinned",
                )
            )
        else:
            self._pin_track(SelectedTrack(path=path, name=path.stem, kind="demo", genre="Demo", bpm="", source="Pinned"))

    def _remove_pinned_track(self) -> None:
        sel = self.selected_tree.selection()
        if not sel:
            return
        iid = sel[0]
        before = len(self._pinned_tracks)
        self._pinned_tracks = [t for t in self._pinned_tracks if t.iid != iid]
        if len(self._pinned_tracks) < before:
            self.refresh_selected_tracks()
            self.selected_status.set("Removed pinned track")
        else:
            self.selected_status.set("Only pinned tracks can be removed — library tracks follow the dropdown")

    def play_selected_track(self) -> None:
        sel = self.selected_tree.selection()
        if not sel:
            return
        track = self._track_from_tree_iid(sel[0])
        if not track:
            return
        self._stop_all_playback()
        if track.kind == "demo":
            self._play_demo_track(track.path, self.selected_status)
        elif track.kind == "wav":
            self._play_audio_loop(track.path, self.selected_status)
        elif track.kind == "midi":
            self._play_midi_groove(track.path, self.selected_status)

    def _open_selected_track(self) -> None:
        sel = self.selected_tree.selection()
        if not sel:
            return
        track = self._track_from_tree_iid(sel[0])
        if not track or not track.path.exists():
            messagebox.showerror(APP_NAME, "File not found.")
            return
        import subprocess

        subprocess.Popen(["explorer", "/select,", str(track.path)])

    def _export_selected_track(self) -> None:
        sel = self.selected_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a track first.")
            return
        track = self._track_from_tree_iid(sel[0])
        if not track:
            return
        if track.kind in ("wav", "demo"):
            dest = filedialog.asksaveasfilename(
                title="Save WAV copy",
                defaultextension=".wav",
                initialfile=f"{track.path.stem}.wav",
                filetypes=[("WAV audio", "*.wav"), ("MP3 audio", "*.mp3"), ("All files", "*.*")],
            )
            if not dest:
                return
            import shutil

            shutil.copy2(track.path, dest)
            self.selected_status.set(f"Saved: {Path(dest).name}")
            return
        if track.kind == "midi":
            if not self._ensure_playback_ready():
                return
            default_dir = libraries_root() / "User-Exports"
            default_dir.mkdir(parents=True, exist_ok=True)
            dest = filedialog.asksaveasfilename(
                title="Export groove as WAV",
                defaultextension=".wav",
                initialdir=str(default_dir),
                initialfile=f"{track.path.stem}.wav",
                filetypes=[("WAV audio", "*.wav")],
            )
            if not dest:
                return
            try:
                render_midi_to_wav(track.path, self.engine.kit, Path(dest))
                self.selected_status.set(f"Exported WAV: {Path(dest).name}")
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"Export failed:\n{exc}")

    def apply_mix_preset(self) -> None:
        preset_name = self.preset_var.get()
        preset = self.mixer_presets.get(preset_name)
        if not preset:
            return
        for ch in self.mixer_channels:
            vol = preset.channels.get(ch.name, ch).volume
            if ch.name in self.fader_vars:
                self.fader_vars[ch.name].set(vol * 100)
            self.engine.set_channel_volume(ch.name, vol)
        self.engine.set_room_send(preset.room_send)
        room_pct = int(preset.room_send * 100)
        base = self.status_var.get().split("  •  Mix:")[0]
        self.status_var.set(f"{base}  •  Mix: {preset_name} ({room_pct}% room)")

    def hit_piece(self, piece: str, velocity: int = 100) -> bool:
        """Click a kit region — try every pad that maps to this drum/cymbal."""
        if not self.engine.kit:
            self.status_var.set("Load a kit first (Pack Punk or Pack SFZ)")
            return False
        pads = list(PIECE_TO_PADS.get(piece, []))
        if piece not in self._piece_click_index:
            self._piece_click_index[piece] = 0
        # Round-robin tom / multi-sample pieces for variety
        if piece in ("Tom", "Snare2") and len(pads) > 1:
            idx = self._piece_click_index[piece] % len(pads)
            pads = pads[idx:] + pads[:idx]
            self._piece_click_index[piece] = idx + 1
        for pad in pads:
            if self.hit_pad(pad, velocity):
                return True
        for pad in pads:
            for alias in PAD_ALIASES_ENGINE.get(pad, []):
                if self.hit_pad(alias, velocity):
                    return True
        self.status_var.set(f"No sample for {piece} in this kit")
        return False

    def hit_pad(self, pad_name: str, velocity: int = 100) -> bool:
        targets = [pad_name] + PAD_ALIASES_ENGINE.get(pad_name, [])
        for target in targets:
            if self.engine.trigger_pad(target, velocity):
                return True
        return False

    def _match_source_busy(self) -> bool:
        return self._recording_guitar or self._analyzing_guitar

    def _match_idle_status(self) -> str:
        gpu = get_gpu_info()
        accel = gpu.label if gpu.available else "CPU (run source\\install-gpu.ps1 for NVIDIA GPU)"
        return f"Record, import, or select a track — AI analysis on {accel}"

    def _clear_match_mode(self) -> None:
        self._match_mode = False
        self._last_matches = []
        self._update_matches_tab_label()
        if hasattr(self, "matches_tree"):
            self.matches_tree.delete(*self.matches_tree.get_children())
            self.matches_context.set("Record, import, or select a track — matches appear here after Find Matches")
            self.matches_status.set("No matches yet")
        self.match_status.set(self._match_idle_status())
        self.refresh_groove_list()

    def _recording_path(self) -> Path:
        return libraries_root() / "User-Recordings" / "guitar_take.wav"

    def _open_last_in_audacity(self) -> None:
        path = self._last_recording_path or self._recording_path()
        try:
            open_in_audacity(path)
        except FileNotFoundError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.match_status.set(f"Opened in Audacity: {path.name}")

    def _audacity_status_prefix(self, path: Path) -> str:
        if not self._open_in_audacity_after_record.get():
            return ""
        try:
            open_in_audacity(path)
            return f"Opened in Audacity: {path.name}  •  "
        except FileNotFoundError as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return ""

    def _import_track(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Import track for matching",
            filetypes=[
                ("Audio", "*.wav;*.mp3;*.flac;*.ogg"),
                ("WAV audio", "*.wav"),
                ("MP3 audio", "*.mp3"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        path = Path(paths[0])
        if len(paths) > 1:
            messagebox.showinfo(
                APP_NAME,
                f"Analyzing first file: {path.name}\n({len(paths)} selected — run Match again for others.)",
            )
        self._last_recording_path = path
        self._analyze_match_source(path)

    def _import_guitar(self) -> None:
        """Backward-compatible alias."""
        self._import_track()

    def _record_guitar(self) -> None:
        out = libraries_root() / "User-Recordings" / "guitar_take.wav"
        secs = max(4, min(30, int(self._record_seconds.get())))
        self._recording_guitar = True
        self.match_status.set(f"Recording {secs}s from microphone — play guitar or any instrument...")
        self.update_idletasks()

        def work() -> None:
            try:
                record_guitar(out, duration_sec=float(secs))
            except Exception as exc:
                def fail(e=exc) -> None:
                    self._recording_guitar = False
                    messagebox.showerror(
                        APP_NAME,
                        f"Recording failed:\n{e}\n\nCheck mic permissions or use Import Track.",
                    )
                    self.match_status.set(self._match_idle_status())

                self.after(0, fail)
                return

            def recorded() -> None:
                self._recording_guitar = False
                self._last_recording_path = out
                self._analyze_match_source(out, from_record=True)

            self.after(0, recorded)

        threading.Thread(target=work, daemon=True).start()

    def _match_selected_track(self) -> None:
        resolved = self._resolve_selected_match_source()
        if not resolved:
            messagebox.showinfo(
                APP_NAME,
                "Select an audio loop, demo, or groove in Grooves, Ass Kickers, or Selected Tracks,\n"
                "then click Match Selected.\n\n"
                "MIDI grooves are rendered to WAV first (needs a loaded kit).",
            )
            return
        path, label, kind = resolved
        self._last_recording_path = path
        if kind == "midi":
            self._prepare_midi_for_match(path, label)
            return
        self._analyze_match_source(path, label=label)

    def _resolve_selected_match_source(self) -> tuple[Path, str, str] | None:
        sel = self.groove_tree.selection()
        if sel:
            iid = sel[0]
            if iid.startswith("wav:"):
                path = Path(iid[4:])
                return (path, path.name, "wav") if path.exists() else None
            if iid.startswith("mid:"):
                path = Path(iid[4:])
                return (path, path.name, "midi") if path.exists() else None

        sel = self.selected_tree.selection()
        if sel:
            track = self._track_from_tree_iid(sel[0])
            if track and track.path.exists():
                return track.path, track.name, track.kind

        sel = self.demo_tree.selection()
        if sel:
            iid = sel[0]
            if iid.startswith("demo:"):
                path = Path(iid[5:])
                return (path, path.name, "demo") if path.exists() else None
        return None

    def _prepare_midi_for_match(self, midi: Path, label: str) -> None:
        self._analyzing_guitar = True
        self.match_status.set(f"Rendering {label} to WAV for analysis...")
        self.update_idletasks()

        def work() -> None:
            cache_dir = libraries_root() / "User-Recordings" / "Match-Cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            out = cache_dir / f"{midi.stem}.wav"
            try:
                if not out.exists() or out.stat().st_mtime < midi.stat().st_mtime:
                    kit, _, _ = load_groove_playback_kit(self.current_detected)
                    render_midi_to_wav(midi, kit, out)
            except Exception as exc:
                def fail(e=exc) -> None:
                    self._analyzing_guitar = False
                    messagebox.showerror(
                        APP_NAME,
                        f"Could not render MIDI for matching:\n{e}\n\nLoad a kit or pick an audio loop instead.",
                    )
                    self.match_status.set(self._match_idle_status())

                self.after(0, fail)
                return

            def done() -> None:
                self._analyze_match_source(out, label=label)

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _analyze_match_source(self, path: Path, *, from_record: bool = False, label: str = "") -> None:
        display = label or path.name
        self._analyzing_guitar = True
        self.match_status.set(f"Analyzing {display} — wait before Find Matches...")
        self.update_idletasks()

        def work() -> None:
            try:
                analysis = analyze_file(path)
            except Exception as exc:
                def fail(e=exc) -> None:
                    self._analyzing_guitar = False
                    messagebox.showerror(APP_NAME, f"Could not analyze audio:\n{e}")
                    self.match_status.set(self._match_idle_status())

                self.after(0, fail)
                return

            def done() -> None:
                self._analyzing_guitar = False
                self._last_analysis = analysis
                prefix = ""
                if from_record and self._open_in_audacity_after_record.get():
                    prefix = self._audacity_status_prefix(path)
                gpu_note = analysis.gpu_backend if analysis.gpu_backend != "CPU" else get_gpu_info().label
                self.match_status.set(
                    f"{prefix}~{analysis.bpm} BPM  •  Key: {analysis.key_root} {analysis.key_mode}  "
                    f"({analysis.key_confidence:.0%})  •  {analysis.duration_sec:.1f}s  •  {gpu_note}  —  Find Matches"
                )
                self._find_groove_matches()

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _analyze_guitar(self, path: Path) -> None:
        """Backward-compatible alias."""
        self._analyze_match_source(path)

    def _all_grooves_for_match(self) -> tuple[list, list]:
        from groove_catalog import scan_all_grooves

        loop_by_path: dict[Path, object] = {}
        lib_root = libraries_root()
        seen_loop_dirs: set[Path] = set()

        def _add_loops_from(path: Path) -> None:
            resolved = path.resolve()
            if not path.is_dir() or resolved in seen_loop_dirs:
                return
            seen_loop_dirs.add(resolved)
            extra = AudioLoopLibrary()
            extra.scan(path)
            for loop in extra.loops:
                loop_by_path[loop.path.resolve()] = loop

        for lib in self.detected:
            _add_loops_from(lib.path / "Loops")
            for entry in load_manifest().get("libraries", []):
                if entry.get("id") == lib.library_id:
                    lf = entry.get("loops_folder")
                    if lf:
                        _add_loops_from(lib_root / lf)

        demo_loops = self.demo_library.to_audio_loops()
        for loop in demo_loops:
            loop_by_path[loop.path.resolve()] = loop

        if self.current_detected and self.current_detected.library_type in STREAM_LOOP_TYPES:
            for loop in self.stream_loop_library.to_audio_loops():
                loop_by_path[loop.path.resolve()] = loop

        return scan_all_grooves(), list(loop_by_path.values())

    def _find_groove_matches(self) -> None:
        if self._recording_guitar:
            messagebox.showinfo(
                APP_NAME,
                "Still recording — wait until the microphone capture finishes.",
            )
            return
        if self._analyzing_guitar:
            messagebox.showinfo(
                APP_NAME,
                "Still analyzing your track — wait until BPM and key appear in the status bar.",
            )
            return
        if not self._last_analysis:
            messagebox.showinfo(
                APP_NAME,
                "Record, import, or select a track first:\n\n"
                "• Record Guitar — mic capture\n"
                "• Import Track — WAV/MP3/FLAC from disk\n"
                "• Match Selected — pick a loop in Grooves or Ass Kickers",
            )
            return
        if self._match_searching:
            return
        self._match_searching = True
        self.match_status.set("Scanning library and ranking matches — please wait...")
        self.update_idletasks()
        analysis = self._last_analysis

        def work() -> None:
            try:
                midi_grooves, audio_loops = self._all_grooves_for_match()
                if not midi_grooves and not audio_loops:
                    self.after(0, lambda: self._finish_groove_matches([], no_library=True))
                    return
                matches = find_matches(analysis, midi_grooves, audio_loops, limit=60)
                self.after(0, lambda m=matches: self._finish_groove_matches(m))
            except Exception as exc:
                self.after(0, lambda e=exc: self._finish_groove_matches([], error=e))

        threading.Thread(target=work, daemon=True).start()

    def _finish_groove_matches(
        self,
        matches: list,
        *,
        no_library: bool = False,
        error: Exception | None = None,
    ) -> None:
        self._match_searching = False
        if error is not None:
            messagebox.showerror(APP_NAME, f"Match search failed:\n{error}")
            self.match_status.set(self._match_idle_status())
            return
        if no_library:
            messagebox.showinfo(APP_NAME, "No grooves in Libraries folder. Run Import-Libraries.ps1 first.")
            self.match_status.set(self._match_idle_status())
            return
        self._match_mode = True
        self._refresh_matches_tab(matches)
        self._update_matches_tab_label(len(matches))
        if hasattr(self, "browser_notebook") and hasattr(self, "_matches_tab"):
            self.browser_notebook.select(self._matches_tab)
        if matches:
            top = matches[0]
            self.groove_status.set(
                f"Best match: {top.name}  —  {top.score:.0f}%  (see Matches Found tab)"
            )
        else:
            self.groove_status.set("No matches found")

    def _stop_kit_groove_visual(self) -> None:
        for aid in self._groove_visual_after_ids:
            try:
                self.after_cancel(aid)
            except ValueError:
                pass
        self._groove_visual_after_ids.clear()

    def _start_kit_groove_visual(self, path: Path, kit) -> None:
        from audio_prep import PREVIEW_LOOP_COUNT

        hits, duration = extract_groove_visual_hits(path, kit)
        if not hits:
            return
        self._stop_kit_groove_visual()
        gap_ms = 80
        loop_ms = int(max(duration, 0.5) * 1000) + gap_ms
        for loop_idx in range(PREVIEW_LOOP_COUNT):
            base_ms = loop_idx * loop_ms
            for t_sec, piece in hits:
                delay = base_ms + int(t_sec * 1000)
                aid = self.after(delay, lambda p=piece: self.kit_canvas.flash_piece(p))
                self._groove_visual_after_ids.append(aid)

    def _stop_groove(self) -> None:
        self._stop_kit_groove_visual()
        self.groove_player.stop()
        self.audio_loop_player.stop()

    def _play_audio_loop(self, path: Path, status_var: tk.StringVar | None = None) -> None:
        label = status_var or self.groove_status
        label.set(f"Loading: {path.stem}…")
        self.update_idletasks()

        def on_ready() -> None:
            self.after(0, lambda: label.set(f"Playing: {path.stem}  •  ×3"))

        def on_error(exc: Exception) -> None:
            self.after(0, lambda: messagebox.showerror(APP_NAME, f"Could not play loop:\n{exc}"))

        self.audio_loop_player.play_file(path, on_ready=on_ready, on_error=on_error)

    def _play_demo_track(self, path: Path, status_var: tk.StringVar | None = None) -> None:
        label = status_var or self.demo_status
        label.set(f"Loading: {path.stem}…")
        self.update_idletasks()

        def on_ready() -> None:
            self.after(0, lambda: label.set(f"Playing: {path.stem}  •  ×3"))

        def on_error(exc: Exception) -> None:
            self.after(0, lambda: messagebox.showerror(APP_NAME, f"Could not play track:\n{exc}"))

        self.demo_player.play_file(path, on_ready=on_ready, on_error=on_error)

    def _play_midi_groove(self, path: Path, status_var: tk.StringVar | None = None) -> None:
        kind = classify_groove_midi(path)
        if needs_playback_fallback(self.current_detected) or not (
            self.engine.kit and self.engine.sample_count() > 0
        ):
            if not self._ensure_groove_kit():
                return
            kit = self._groove_kit
            groove_label = self._groove_kit_label
        else:
            kit = self.engine.kit
            groove_label = self._playback_kit_label or (kit.name if kit else "")
        label = status_var or self.groove_status
        label.set(f"Rendering: {path.stem}…")
        self.update_idletasks()

        kind_tag = f"  •  {kind} preview" if kind != "drums" else ""

        def on_ready() -> None:
            def start() -> None:
                self._start_kit_groove_visual(path, kit)
                label.set(f"Playing: {path.stem}  •  {groove_label}{kind_tag}  •  ×3  •  kit lights follow groove")

            self.after(0, start)

        def on_error(exc: Exception) -> None:
            def show() -> None:
                label.set(f"Playback failed: {path.stem}")
                messagebox.showerror(APP_NAME, f"Could not play groove:\n{exc}")

            self.after(0, show)

        self.groove_player.play_file(
            path,
            kit,
            channel_volume=dict(self.engine.channel_volume),
            master_volume=self.engine.master_volume,
            on_ready=on_ready,
            on_error=on_error,
        )

    def _stop_all_playback(self) -> None:
        self._stop_groove()
        self.demo_player.stop()

    def _load_demos(self) -> None:
        root = libraries_root() / "Demo-Tracks"
        count = self.demo_library.load(root)
        sections = ["All"] + [s["heading"] for s in self.demo_library.sections]
        self.demo_section_combo["values"] = sections
        genres = ["All"] + self.demo_library.genres()
        self.demo_genre_combo["values"] = genres
        if sections:
            self.demo_section_var.set("All")
        if genres:
            self.demo_genre_var.set("All")
        self.refresh_demo_list()
        if count:
            self.demo_status.set(f"{count} Ass Kickers loaded from {root.name}")
        else:
            self.demo_status.set("No Ass Kickers — click Refresh or run Import-SSD-Demos.ps1")

    def _import_ssd_demos(self) -> None:
        from ssd_demo_import import build_default_catalog, download_catalog

        dest = libraries_root() / "Demo-Tracks"
        self.demo_status.set("Fetching Ass Kickers from stevenslatedrums.com...")
        self.update_idletasks()
        try:
            catalog = build_default_catalog()
            download_catalog(catalog, dest)
            self._load_demos()
            self.demo_status.set(f"Imported {len(self.demo_library.tracks)} Ass Kickers")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Ass Kickers import failed:\n{exc}")

    def refresh_demo_list(self) -> None:
        self.demo_tree.delete(*self.demo_tree.get_children())
        self._demo_items.clear()
        query = self.demo_search.get()
        section = self.demo_section_var.get()
        genre = self.demo_genre_var.get()
        tracks = self.demo_library.filter(query, genre)
        if section and section != "All":
            tracks = [t for t in tracks if t.section_heading == section]
        for track in tracks:
            iid = f"demo:{track.path}"
            self._demo_items.append((iid, track.path))
            self.demo_tree.insert(
                "",
                "end",
                iid=iid,
                values=(track.genre, track.section_heading, track.subtitle[:60], track.title),
            )

    def play_selected_demo(self) -> None:
        sel = self.demo_tree.selection()
        if not sel:
            return
        path = Path(sel[0][5:])
        self._stop_all_playback()
        self._play_demo_track(path)

    def _open_demo_file(self) -> None:
        sel = self.demo_tree.selection()
        if not sel:
            return
        path = Path(sel[0][5:])
        import subprocess

        if path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            messagebox.showerror(APP_NAME, f"File not found:\n{path}")

    def _export_demo(self) -> None:
        sel = self.demo_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select an Ass Kicker first.")
            return
        path = Path(sel[0][5:])
        default_dir = libraries_root() / "User-Exports"
        default_dir.mkdir(parents=True, exist_ok=True)
        dest = filedialog.asksaveasfilename(
            title="Export Ass Kicker as WAV",
            defaultextension=".wav",
            initialdir=str(default_dir),
            initialfile=f"{path.stem}.wav",
            filetypes=[("WAV audio", "*.wav"), ("MP3 audio", "*.mp3")],
        )
        if not dest:
            return
        try:
            if Path(dest).suffix.lower() == ".mp3":
                import shutil

                shutil.copy2(path, dest)
            else:
                from wav_io import load_audio_mono, write_wav_mono

                samples, sr = load_audio_mono(path)
                write_wav_mono(Path(dest), samples, sr)
            self.demo_status.set(f"Exported: {Path(dest).name} — drag into your DAW")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Export failed:\n{exc}")

    def refresh_groove_list(self) -> None:
        self.groove_tree.delete(*self.groove_tree.get_children())
        q = self.groove_search.get().strip().lower()

        for groove in self.groove_library.filter(q):
            iid = f"mid:{groove.path.resolve()}"
            if self.groove_tree.exists(iid):
                continue
            self.groove_tree.insert("", "end", iid=iid, values=(groove.genre or "MIDI", groove.bpm, "", "", groove.name))

        for loop in self.audio_loop_library.filter(q):
            iid = f"wav:{loop.path.resolve()}"
            if self.groove_tree.exists(iid):
                continue
            genre = loop.genre or "Loop"
            self.groove_tree.insert("", "end", iid=iid, values=(genre, loop.bpm, loop.pack, "", loop.name))

    def _open_groove_file(self) -> None:
        sel = self.groove_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.startswith("wav:"):
            path = Path(iid[4:])
        elif iid.startswith("mid:"):
            path = Path(iid[4:])
        else:
            return
        import os
        import subprocess

        if path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            messagebox.showerror(APP_NAME, f"File not found:\n{path}")

    def _export_groove_wav(self) -> None:
        sel = self.groove_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a groove in the list first.")
            return
        iid = sel[0]
        if iid.startswith("wav:"):
            src = Path(iid[4:])
            dest = filedialog.asksaveasfilename(
                title="Save WAV copy",
                defaultextension=".wav",
                initialfile=f"{src.stem}.wav",
                filetypes=[("WAV audio", "*.wav")],
            )
            if not dest:
                return
            import shutil

            shutil.copy2(src, dest)
            self.groove_status.set(f"Saved: {Path(dest).name}")
            return

        if not iid.startswith("mid:"):
            return
        if not self.engine.kit or self.engine.sample_count() == 0:
            if not self._ensure_playback_ready():
                return

        midi_path = Path(iid[4:])
        default_dir = libraries_root() / "User-Exports"
        default_dir.mkdir(parents=True, exist_ok=True)
        dest = filedialog.asksaveasfilename(
            title="Export groove as WAV",
            defaultextension=".wav",
            initialdir=str(default_dir),
            initialfile=f"{midi_path.stem}.wav",
            filetypes=[("WAV audio", "*.wav")],
        )
        if not dest:
            return
        try:
            render_midi_to_wav(midi_path, self.engine.kit, Path(dest))
            self.groove_status.set(f"Exported WAV: {Path(dest).name} — drag into your DAW")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Export failed:\n{exc}")

    def play_selected_groove(self) -> None:
        sel = self.groove_tree.selection()
        if not sel:
            return
        iid = sel[0]
        self._stop_all_playback()
        if iid.startswith("wav:"):
            self._play_audio_loop(Path(iid[4:]), self.groove_status)
        elif iid.startswith("mid:"):
            self._play_midi_groove(Path(iid[4:]), self.groove_status)

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

    def _show_libraries_dialog(self) -> None:
        win = tk.Toplevel(self)
        win.title("Libraries")
        win.geometry("520x420")
        win.configure(bg=THEME["panel"])
        text = tk.Text(win, bg=THEME["panel2"], fg=THEME["text"], wrap="word", relief="flat")
        text.pack(fill="both", expand=True, padx=12, pady=12)
        root = libraries_root()
        manifest = load_manifest()
        lines = [f"{APP_NAME} — local libraries\n", f"Folder: {root}\n"]
        for d in self.detected:
            lines.append(f"• {d.name}: {d.wav_count:,} samples, {d.midi_count:,} grooves")
        extras = manifest.get("extras", {})
        for key, folder in extras.items():
            path = root / folder
            if path.is_dir():
                wavs = sum(1 for _ in path.rglob("*.wav"))
                mids = sum(1 for _ in path.rglob("*.mid"))
                ptn = sum(1 for _ in path.rglob("*.ptn"))
                label = key.replace("_", " ").title()
                detail = f"{wavs} wav" if wavs else f"{mids} mid" if mids else f"{ptn} patterns"
                lines.append(f"• {label}: {detail} ({folder})")
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
        custom = add_custom_library(Path(chosen))
        self.detected = detect_all() + [custom]
        labels = []
        for d in self.detected:
            if d.playable_wav_count:
                labels.append(f"{d.name}  ({d.playable_wav_count:,} playable samples)")
            elif d.library_type == "pdk" and d.playable_wav_count == 0:
                labels.append(f"{d.name}  (PDK — select to extract samples)")
            elif d.library_type == "vst":
                labels.append(f"{d.name}  (VST3 plugin — use in your DAW)")
            elif d.sample_format == "ttpw":
                labels.append(f"{d.name}  (Toontrack format — kit won't play here)")
            else:
                labels.append(f"{d.name}  ({d.wav_count:,} samples)")
        self.library_combo["values"] = labels
        self.library_combo.current(len(labels) - 1)
        self.on_library_change()


def main() -> None:
    app = DrummerStudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
