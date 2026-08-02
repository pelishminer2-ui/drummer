"""Scan and play MIDI groove libraries."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import mido

from audio_prep import PREVIEW_LOOP_COUNT
from groove_render import buffer_to_pygame_sound, render_midi_to_buffer
from library_parser import DrumKit


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
    """Play MIDI grooves as one pre-rendered audio stream — smooth like WAV/MP3."""

    def __init__(self) -> None:
        self._channel = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.playing = False
        self._render_cache: dict[tuple, object] = {}

    def stop(self) -> None:
        self._stop.set()
        if self._channel:
            try:
                self._channel.stop()
            except Exception:
                pass
        self._channel = None
        self.playing = False

    def play_file(
        self,
        path: Path,
        kit: DrumKit,
        *,
        channel_volume: dict[str, float] | None = None,
        master_volume: float = 1.0,
        on_ready: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(path, kit, channel_volume or {}, master_volume, on_ready, on_error),
            daemon=True,
        )
        self._thread.start()

    def _cache_key(self, path: Path, kit: DrumKit, channel_volume: dict[str, float], master_volume: float) -> tuple:
        mtime = path.stat().st_mtime if path.exists() else 0
        vol_key = tuple(sorted((k, round(v, 3)) for k, v in channel_volume.items()))
        return (str(path.resolve()), mtime, kit.name, vol_key, round(master_volume, 3))

    def _run(
        self,
        path: Path,
        kit: DrumKit,
        channel_volume: dict[str, float],
        master_volume: float,
        on_ready: Callable[[], None] | None,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        self.playing = True
        try:
            key = self._cache_key(path, kit, channel_volume, master_volume)
            sound = self._render_cache.get(key)
            if sound is None:
                if self._stop.is_set():
                    return
                mono = render_midi_to_buffer(
                    path,
                    kit,
                    channel_volume=channel_volume,
                    master_volume=master_volume,
                )
                if self._stop.is_set():
                    return
                sound = buffer_to_pygame_sound(mono)
                if len(self._render_cache) > 24:
                    self._render_cache.clear()
                self._render_cache[key] = sound

            if self._stop.is_set():
                return
            if on_ready:
                on_ready()

            for loop_idx in range(PREVIEW_LOOP_COUNT):
                if self._stop.is_set():
                    break
                channel = sound.play()
                if not channel:
                    raise RuntimeError("Audio playback failed — check mixer / sound device.")
                self._channel = channel
                while channel.get_busy():
                    if self._stop.is_set():
                        channel.stop()
                        break
                    time.sleep(0.05)
                if self._stop.is_set():
                    break
                if loop_idx < PREVIEW_LOOP_COUNT - 1:
                    time.sleep(0.08)
        except Exception as exc:
            self.playing = False
            if on_error:
                on_error(exc)
            return
        finally:
            self.playing = False
            self._channel = None
