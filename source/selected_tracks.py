"""Tracks for the library + kit chosen in the toolbar dropdowns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from audio_loops import AudioLoopLibrary
from library_scanner import DetectedLibrary, libraries_root, load_manifest
from midi_grooves import GrooveLibrary


@dataclass(frozen=True)
class SelectedTrack:
    path: Path
    name: str
    kind: str  # midi | wav | demo
    genre: str
    bpm: str
    source: str

    @property
    def iid(self) -> str:
        return f"{self.kind}:{self.path.resolve()}"


def _loop_roots(detected: DetectedLibrary) -> list[Path]:
    roots: list[Path] = []
    lib_root = libraries_root()
    loops_dir = detected.path / "Loops"
    if loops_dir.is_dir():
        roots.append(loops_dir)
    for entry in load_manifest().get("libraries", []):
        if entry.get("id") == detected.library_id:
            lf = entry.get("loops_folder")
            if lf:
                lp = lib_root / lf
                if lp.is_dir() and lp not in roots:
                    roots.append(lp)
    return roots


def tracks_for_library(detected: DetectedLibrary | None, kit_name: str = "") -> list[SelectedTrack]:
    """MIDI grooves + WAV loops tied to the active library dropdown."""
    if not detected:
        return []

    source = f"{detected.name} • {kit_name}" if kit_name else detected.name
    tracks: list[SelectedTrack] = []
    seen: set[str] = set()

    if detected.midi_root and detected.midi_root.is_dir():
        lib = GrooveLibrary()
        lib.scan(detected.midi_root)
        for groove in lib.grooves:
            key = str(groove.path.resolve())
            if key in seen:
                continue
            seen.add(key)
            tracks.append(
                SelectedTrack(
                    path=groove.path,
                    name=groove.name,
                    kind="midi",
                    genre=groove.genre or "MIDI",
                    bpm=groove.bpm,
                    source=source,
                )
            )

    loop_lib = AudioLoopLibrary()
    for root in _loop_roots(detected):
        extra = AudioLoopLibrary()
        extra.scan(root)
        loop_lib.loops.extend(extra.loops)

    for loop in loop_lib.loops:
        key = str(loop.path.resolve())
        if key in seen:
            continue
        seen.add(key)
        tracks.append(
            SelectedTrack(
                path=loop.path,
                name=loop.name,
                kind="wav",
                genre=loop.genre,
                bpm=loop.bpm,
                source=source,
            )
        )

    tracks.sort(key=lambda t: (0 if t.kind == "demo" else 1 if t.kind == "midi" else 2, t.name.lower()))
    return tracks
