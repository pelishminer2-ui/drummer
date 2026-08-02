"""BPM labels for MIDI grooves — parse paths, read tempo, disk cache."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import mido

from library_scanner import libraries_root
from mido_compat import MIDI_READ_ERRORS

_CACHE_NAME = "groove-tempo-cache.json"
_BPM_IN_TEXT = re.compile(r"(\d{2,3})\s*-\s*(\d{2,3})\s*bpm", re.I)
_BPM_SINGLE = re.compile(r"(\d{2,3})\s*bpm", re.I)
_BPM_FOLDER = re.compile(r"(\d{2,3})#(\d{2,3})")


def _cache_path() -> Path:
    return libraries_root() / _CACHE_NAME


def _load_disk_cache() -> dict[str, dict[str, float | int | str]]:
    path = _cache_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_disk_cache(cache: dict[str, dict[str, float | int | str]]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=0), encoding="utf-8")


def _bpm_from_path_text(path: Path) -> str:
    text = f"{path} {path.stem}"
    range_match = _BPM_IN_TEXT.search(text)
    if range_match:
        return f"{range_match.group(1)}-{range_match.group(2)}"
    single = _BPM_SINGLE.search(text)
    if single:
        return single.group(1)
    folder = _BPM_FOLDER.search(text)
    if folder:
        lo, hi = int(folder.group(1)), int(folder.group(2))
        if 40 <= lo <= 300 and 40 <= hi <= 300:
            return f"{min(lo, hi)}-{max(lo, hi)}"
    return ""


@lru_cache(maxsize=16384)
def _read_midi_tempo_bpm(path_str: str, mtime_ns: int) -> float | None:
    path = Path(path_str)
    if not path.is_file():
        return None
    try:
        midi = mido.MidiFile(str(path))
    except MIDI_READ_ERRORS:
        return None
    tempo = 500000
    for track in midi.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                tempo = msg.tempo
                return round(float(mido.tempo2bpm(tempo)), 1)
    return round(float(mido.tempo2bpm(tempo)), 1)


def groove_bpm_label(path: Path, catalog_label: str = "") -> str:
    """Best BPM label for a groove path (catalog, filename, MIDI tempo, cache)."""
    label = (catalog_label or "").strip()
    if label and label != "?":
        return label

    from_path = _bpm_from_path_text(path)
    if from_path:
        return from_path

    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return "?"

    key = str(path.resolve())
    disk = _load_disk_cache()
    entry = disk.get(key)
    if entry and entry.get("mtime_ns") == mtime_ns and "bpm" in entry:
        bpm = float(entry["bpm"])
        return str(int(round(bpm)))

    bpm = _read_midi_tempo_bpm(key, mtime_ns)
    if bpm is None:
        return "?"

    disk[key] = {"mtime_ns": mtime_ns, "bpm": bpm}
    _save_disk_cache(disk)
    return str(int(round(bpm)))


def warm_bpm_cache(paths: list[Path], on_progress: Callable[[int, int], None] | None = None) -> None:
    """Pre-read MIDI tempos so the first Find Matches is responsive."""
    total = len(paths)
    for i, path in enumerate(paths):
        if path.suffix.lower() != ".mid":
            continue
        groove_bpm_label(path)
        if on_progress and (i % 250 == 0 or i + 1 == total):
            on_progress(i + 1, total)
