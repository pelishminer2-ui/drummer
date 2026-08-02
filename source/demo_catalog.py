"""Play imported web demo tracks (Drummer-branded SSD / Trigger / Genre demos)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pygame


@dataclass
class DemoTrack:
    section_id: str
    section_heading: str
    index: int
    title: str
    subtitle: str
    path: Path
    genre: str = ""


class DemoLibrary:
    def __init__(self) -> None:
        self.tracks: list[DemoTrack] = []
        self.sections: list[dict] = []

    def load(self, root: Path) -> int:
        self.tracks.clear()
        self.sections.clear()
        manifest = root / "manifest.json"
        if not manifest.exists():
            return 0
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for section in data.get("sections", []):
            heading = section.get("heading", section.get("id", "Demos"))
            self.sections.append({"id": section.get("id"), "heading": heading})
            for track in section.get("tracks", []):
                rel = track.get("file")
                if not rel:
                    continue
                path = root / rel
                if not path.exists():
                    continue
                self.tracks.append(
                    DemoTrack(
                        section_id=section.get("id", ""),
                        section_heading=heading,
                        index=int(track.get("index", 0)),
                        title=track.get("title", path.stem),
                        subtitle=track.get("subtitle", ""),
                        path=path,
                        genre=track.get("genre", ""),
                    )
                )
        return len(self.tracks)

    def genres(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for track in self.tracks:
            g = track.genre.strip()
            if g and g not in seen:
                seen.add(g)
                out.append(g)
        return sorted(out, key=str.lower)

    def filter(self, query: str, genre: str = "") -> list[DemoTrack]:
        q = query.strip().lower()
        g = genre.strip().lower()
        out = self.tracks
        if g and g != "all":
            out = [t for t in out if t.genre.lower() == g]
        if not q:
            return out
        return [
            t
            for t in out
            if q in t.title.lower()
            or q in t.subtitle.lower()
            or q in t.section_heading.lower()
            or q in t.genre.lower()
        ]

    def to_audio_loops(self) -> list:
        from audio_loops import AudioLoopInfo

        return [
            AudioLoopInfo(
                path=t.path,
                name=t.title,
                bpm="",
                genre=t.genre or "Ass Kickers",
                pack=t.section_heading,
            )
            for t in self.tracks
        ]


class DemoPlayer:
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

    def play_file(self, path: Path, *, on_ready=None, on_error=None) -> None:
        self.stop()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(path, on_ready, on_error),
            daemon=True,
        )
        self._thread.start()

    def _run(self, path: Path, on_ready, on_error) -> None:
        from audio_prep import PREVIEW_LOOP_COUNT, ensure_pygame_mixer

        self.playing = True
        try:
            ensure_pygame_mixer()
            sound = pygame.mixer.Sound(str(path))
            if self._stop.is_set():
                return
            if on_ready:
                on_ready()
            for loop_idx in range(PREVIEW_LOOP_COUNT):
                if self._stop.is_set():
                    break
                self._channel = sound.play()
                if not self._channel:
                    raise RuntimeError("Audio playback failed.")
                while self._channel.get_busy():
                    if self._stop.is_set():
                        self._channel.stop()
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
