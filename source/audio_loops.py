"""Scan and play WAV audio loops (in addition to MIDI grooves)."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pygame

from audio_prep import PREVIEW_LOOP_COUNT, ensure_pygame_mixer, wav_to_pygame_sound
from wav_io import is_playable_wav


@dataclass
class AudioLoopInfo:
    path: Path
    name: str
    bpm: str
    genre: str
    pack: str


def _parse_loop_path(rel_parts: tuple[str, ...], filename: str) -> tuple[str, str, str]:
    pack = rel_parts[0] if rel_parts else "Loops"
    bpm = ""
    genre = "Punk"
    for part in rel_parts:
        match = re.search(r"^(\d{2,3})$", part)
        if match:
            bpm = match.group(1)
        match = re.search(r"(\d{2,3})\s*bpm", part, re.I)
        if match:
            bpm = match.group(1)
    if not bpm:
        match = re.search(r"^(\d{2,3})_", filename)
        if match:
            bpm = match.group(1)
    if "fill" in filename.lower():
        genre = "Fill"
    elif "hh_" in filename.lower() or "ohh" in filename.lower():
        genre = "Hat Pattern"
    elif "rc_" in filename.lower() or "ride" in filename.lower():
        genre = "Ride Pattern"
    return pack, bpm, genre


class AudioLoopLibrary:
    def __init__(self) -> None:
        self.loops: list[AudioLoopInfo] = []

    def scan(self, root: Path) -> int:
        if not root or not root.is_dir():
            return 0
        added = 0
        for wav in sorted(root.rglob("*.wav")):
            rel = wav.relative_to(root)
            pack, bpm, genre = _parse_loop_path(rel.parts[:-1], wav.stem)
            self.loops.append(
                AudioLoopInfo(path=wav, name=wav.stem, bpm=bpm, genre=genre, pack=pack)
            )
            added += 1
        return added

    def filter(self, query: str) -> list[AudioLoopInfo]:
        q = query.strip().lower()
        if not q:
            return self.loops
        return [
            loop for loop in self.loops
            if q in loop.name.lower() or q in loop.bpm.lower() or q in loop.genre.lower() or q in loop.pack.lower()
        ]


class AudioLoopPlayer:
    def __init__(self) -> None:
        self._channel: pygame.mixer.Channel | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.playing = False

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
        *,
        on_ready: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(path, on_ready, on_error),
            daemon=True,
        )
        self._thread.start()

    def _load_sound(self, path: Path) -> pygame.mixer.Sound:
        ensure_pygame_mixer()
        if path.suffix.lower() in {".mp3", ".ogg", ".flac"}:
            return pygame.mixer.Sound(str(path))
        if not is_playable_wav(path):
            raise ValueError(f"Not a standard WAV file: {path.name}")
        return wav_to_pygame_sound(path)

    def _run(
        self,
        path: Path,
        on_ready: Callable[[], None] | None,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        self.playing = True
        try:
            sound = self._load_sound(path)
            if self._stop.is_set():
                return
            if on_ready:
                on_ready()
            for loop_idx in range(PREVIEW_LOOP_COUNT):
                if self._stop.is_set():
                    break
                channel = sound.play()
                if not channel:
                    raise RuntimeError("Audio playback failed.")
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
