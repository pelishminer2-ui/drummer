"""Scan all of F:\\Drummer\\Libraries for groove matching after a recording."""

from __future__ import annotations

import re
from pathlib import Path

from audio_loops import AudioLoopInfo, _parse_loop_path
from library_scanner import libraries_root
from midi_drum_map import classify_groove_midi
from midi_grooves import GrooveInfo, _parse_midi_path
from wav_io import is_playable_wav

_SKIP_DIR_NAMES = frozenset(
    {
        "user-recordings",
        "user-exports",
        "click-sounds",
        "_staging",
        "drag-cache",
        "match-cache",
        "sounds",
        "inbox",
    }
)

_LOOP_DIR_NAMES = frozenset({"loops", "demo-tracks", "grooves"})
_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def _path_parts_lower(path: Path, root: Path) -> set[str]:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return {p.lower() for p in rel.parts}


def _skip_for_match(path: Path, root: Path) -> bool:
    parts = _path_parts_lower(path, root)
    if parts & _SKIP_DIR_NAMES:
        return True
    if "user-recordings" in str(path).lower():
        return True
    name = path.name.lower()
    if name in {"guitar_take.wav", "desktop.ini"}:
        return True
    return False


def _is_drum_groove_candidate(path: Path) -> bool:
    if path.suffix.lower() not in {".mid", ".midi"}:
        return False
    kind = classify_groove_midi(path)
    if kind != "drums":
        return False
    stem = path.stem.lower()
    if stem.endswith("_fx") or "sound fx" in str(path).lower():
        return False
    return True


def _is_audio_loop_candidate(path: Path, root: Path) -> bool:
    if path.suffix.lower() not in _AUDIO_EXTS:
        return False
    if _skip_for_match(path, root):
        return False
    parts = _path_parts_lower(path, root)
    if parts & _LOOP_DIR_NAMES:
        return True
    if "demo-tracks" in parts:
        return True
    if "cool-imports" in parts and "loops" in parts:
        return True
    # Pack-Punk style: BPM prefix in filename inside a loops-like tree
    if re.search(r"^\d{2,3}_", path.stem) or re.search(r"\d{2,3}\s*bpm", path.stem, re.I):
        if "pack-punk" in parts or "loops" in str(path).lower():
            return True
    return False


def scan_all_midi_grooves(root: Path | None = None) -> list[GrooveInfo]:
    """Every drum MIDI groove under Libraries (all packs and folders)."""
    lib_root = (root or libraries_root()).resolve()
    if not lib_root.is_dir():
        return []

    grooves: list[GrooveInfo] = []
    seen: set[Path] = set()
    for midi in sorted(lib_root.rglob("*")):
        if midi.suffix.lower() not in {".mid", ".midi"}:
            continue
        if _skip_for_match(midi, lib_root):
            continue
        if not _is_drum_groove_candidate(midi):
            continue
        key = midi.resolve()
        if key in seen:
            continue
        seen.add(key)
        try:
            rel_parts = midi.relative_to(lib_root).parts[:-1]
        except ValueError:
            rel_parts = midi.parts[:-1]
        pack, style, genre, bpm, time_sig = _parse_midi_path(rel_parts)
        grooves.append(
            GrooveInfo(
                path=midi,
                name=midi.stem,
                pack=pack,
                style=style,
                genre=genre,
                bpm=bpm,
                time_sig=time_sig,
            )
        )
    return grooves


def _parse_mp3_loop(path: Path, root: Path) -> AudioLoopInfo:
    try:
        rel_parts = path.relative_to(root).parts[:-1]
    except ValueError:
        rel_parts = path.parts[:-1]
    pack, bpm, genre = _parse_loop_path(rel_parts, path.stem)
    if not bpm:
        m = re.search(r"(\d{2,3})\s*bpm", path.stem, re.I)
        if m:
            bpm = m.group(1)
    return AudioLoopInfo(path=path, name=path.stem, bpm=bpm, genre=genre, pack=pack)


def scan_all_audio_loops(root: Path | None = None) -> list[AudioLoopInfo]:
    """WAV/MP3/FLAC loops under Libraries (Loops, Demo-Tracks, stream packs, etc.)."""
    lib_root = (root or libraries_root()).resolve()
    if not lib_root.is_dir():
        return []

    loops: list[AudioLoopInfo] = []
    seen: set[Path] = set()
    for path in sorted(lib_root.rglob("*")):
        if path.suffix.lower() not in _AUDIO_EXTS:
            continue
        if not _is_audio_loop_candidate(path, lib_root):
            continue
        if path.suffix.lower() == ".wav" and not is_playable_wav(path):
            continue
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        loops.append(_parse_mp3_loop(path, lib_root))
    return loops


def scan_libraries_for_match(root: Path | None = None) -> tuple[list[GrooveInfo], list[AudioLoopInfo]]:
    """Full Libraries scan — MIDI grooves + audio loops for Find Matches."""
    lib_root = (root or libraries_root()).resolve()
    midi = scan_all_midi_grooves(lib_root)
    audio = scan_all_audio_loops(lib_root)
    return midi, audio
