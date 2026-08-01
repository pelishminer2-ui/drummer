"""Scan and play MIDI groove libraries."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import mido


@dataclass
class GrooveInfo:
    path: Path
    name: str
    pack: str
    style: str
    genre: str = ""
    bpm: str = ""
    time_sig: str = ""


def _parse_midi_path(rel_parts: tuple[str, ...]) -> tuple[str, str, str, str, str]:
    pack = rel_parts[0].replace("@", " / ") if rel_parts else "General"
    style = rel_parts[1].replace("@", " / ") if len(rel_parts) > 2 else ""
    genre = ""
    bpm = ""
    time_sig = ""

    for part in rel_parts:
        cleaned = part.replace("@", " ")
        if "#" in part and "BPM" in part.upper():
            bpm_match = re.search(r"(\d+)\s*-\s*(\d+)\s*BPM", part, re.I)
            if bpm_match:
                bpm = f"{bpm_match.group(1)}-{bpm_match.group(2)}"
            ts_match = re.search(r"(\d)#(\d)", part)
            if ts_match:
                time_sig = f"{ts_match.group(1)}/{ts_match.group(2)}"
        if any(g in part.upper() for g in ("POP", "ROCK", "FUNK", "BALLAD", "MOTOWN", "SAMBA", "BAIAO", "SHUFFLE", "SIDESTICK")):
            genre = cleaned.split("_", 1)[-1].strip()
        if part in ("Drums", "Groove Monkee", "SmartLoops", "Bass") or "Groove Monkee" in part:
            if not genre and len(rel_parts) > 1:
                genre = rel_parts[1].replace("@", " ")

    return pack, style, genre, bpm, time_sig


class GrooveLibrary:
    def __init__(self) -> None:
        self.grooves: list[GrooveInfo] = []

    def scan(self, midi_root: Path) -> int:
        self.grooves.clear()
        if not midi_root.is_dir():
            return 0

        for midi_path in sorted(midi_root.rglob("*.mid")):
            rel = midi_path.relative_to(midi_root)
            pack, style, genre, bpm, time_sig = _parse_midi_path(rel.parts)
            self.grooves.append(
                GrooveInfo(
                    path=midi_path,
                    name=midi_path.stem,
                    pack=pack,
                    style=style,
                    genre=genre,
                    bpm=bpm,
                    time_sig=time_sig,
                )
            )
        return len(self.grooves)

    def filter(self, query: str) -> list[GrooveInfo]:
        q = query.strip().lower()
        if not q:
            return self.grooves
        return [
            g for g in self.grooves
            if q in g.name.lower() or q in g.pack.lower() or q in g.style.lower()
            or q in g.genre.lower() or q in g.bpm.lower()
        ]


class GroovePlayer:
    def __init__(self, trigger_callback) -> None:
        self._trigger = trigger_callback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.playing = False

    def stop(self) -> None:
        self._stop.set()
        self.playing = False

    def play_file(self, path: Path) -> None:
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(path,), daemon=True)
        self._thread.start()

    def _run(self, path: Path) -> None:
        self.playing = True
        try:
            midi = mido.MidiFile(str(path))
            tempo = 500000
            events: list[tuple[float, int, int]] = []

            for track in midi.tracks:
                tick = 0
                track_tempo = tempo
                for msg in track:
                    tick += msg.time
                    if msg.type == "set_tempo":
                        track_tempo = msg.tempo
                    if msg.type == "note_on" and msg.velocity > 0:
                        sec = mido.tick2second(tick, midi.ticks_per_beat, track_tempo)
                        events.append((sec, msg.note, msg.velocity))

            events.sort(key=lambda item: item[0])
            start = time.perf_counter()
            for sec, note, velocity in events:
                if self._stop.is_set():
                    break
                wait = sec - (time.perf_counter() - start)
                if wait > 0:
                    time.sleep(wait)
                self._trigger(note, velocity)
        finally:
            self.playing = False
