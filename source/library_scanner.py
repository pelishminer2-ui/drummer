"""Detect drum libraries under the local Libraries folder."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from wav_io import count_playable_wavs, first_wav_format


@dataclass
class DetectedLibrary:
    path: Path
    name: str
    library_id: str
    wav_count: int
    playable_wav_count: int
    sample_format: str  # wave | ttpw | mixed | none
    midi_root: Path | None
    midi_count: int
    library_type: str = "wav"  # wav | sfz | folder
    kit_labels: dict[str, str] = field(default_factory=dict)
    sfz_kits: list[dict] = field(default_factory=list)


def _project_root() -> Path:
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parent.parent


def libraries_root() -> Path:
    return _project_root() / "Libraries"


def load_manifest() -> dict:
    manifest_path = libraries_root() / "manifest.json"
    if not manifest_path.exists():
        return {"libraries": [], "groove_roots": []}
    raw = manifest_path.read_text(encoding="utf-8-sig").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Recover from truncated/duplicate JSON (take first complete object)
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(raw)
        return data


def _count_wavs(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("*.wav"))


def _count_playable(root: Path) -> int:
    sounds = root / "Sounds"
    if sounds.is_dir():
        return count_playable_wavs(sounds)
    return count_playable_wavs(root)


def _sample_format(root: Path) -> str:
    sounds = root / "Sounds"
    probe = sounds if sounds.is_dir() else root
    kind = first_wav_format(probe)
    return kind or "none"


def _count_midi(root: Path | None) -> int:
    if not root or not root.is_dir():
        return 0
    return len(list(root.rglob("*.mid")))


def _count_audio_loops(root: Path) -> int:
    if not root.is_dir():
        return 0
    exts = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
    loops = root / "Loops"
    search = loops if loops.is_dir() else root
    return sum(1 for p in search.rglob("*.*") if p.suffix.lower() in exts)


def _resolve_midi_root(libraries_root: Path, manifest_entry: dict) -> Path | None:
    midi_folder = manifest_entry.get("midi_folder")
    if not midi_folder:
        return None
    candidate = libraries_root / midi_folder
    return candidate if candidate.is_dir() else None


def detect_all() -> list[DetectedLibrary]:
    root = libraries_root()
    manifest = load_manifest()
    found: list[DetectedLibrary] = []

    for entry in manifest.get("libraries", []):
        folder = entry.get("folder", "")
        lib_path = root / folder
        if not lib_path.is_dir():
            continue

        lib_type = entry.get("type", "wav")
        midi_root = _resolve_midi_root(root, entry)
        midi_count = _count_midi(midi_root)
        if lib_type == "pdk":
            sounds = lib_path / "Sounds"
            if sounds.is_dir() and any(sounds.rglob("*.wav")):
                playable = count_playable_wavs(sounds)
            elif (lib_path / entry.get("pdk_file", "MT-PowerDrumKit-Content.pdk")).exists():
                playable = 0
            else:
                playable = 0
            wav_count = _count_wavs(lib_path)
        elif lib_type in ("monkey_alts", "metal_hitters"):
            playable = 0
            wav_count = _count_audio_loops(lib_path)
        elif lib_type == "cool_imports":
            kits_dir = lib_path / "Kits"
            playable = count_playable_wavs(kits_dir) if kits_dir.is_dir() else 0
            if playable == 0:
                playable = count_playable_wavs(lib_path)
            wav_count = _count_wavs(lib_path) + _count_audio_loops(lib_path)
        else:
            playable = _count_playable(lib_path)
            wav_count = _count_wavs(lib_path)

        found.append(
            DetectedLibrary(
                path=lib_path,
                name=entry.get("name", folder),
                library_id=entry.get("id", folder),
                wav_count=wav_count,
                playable_wav_count=playable,
                sample_format=_sample_format(lib_path)
                if lib_type not in ("monkey_alts", "metal_hitters", "cool_imports")
                else "audio",
                midi_root=midi_root,
                midi_count=midi_count,
                library_type=lib_type,
                kit_labels=entry.get("kit_labels", {}),
                sfz_kits=entry.get("kits", []),
            )
        )

    found.sort(key=lambda d: (-d.playable_wav_count, d.name.lower()))
    return found


def add_custom_library(path: Path) -> DetectedLibrary:
    midi_candidates = [path / "Grooves", path / "Midi", path.parent / "Grooves"]
    midi_root = next((p for p in midi_candidates if p.is_dir()), None)
    lib_type = "sfz" if (path / "Drums").is_dir() else "wav"
    return DetectedLibrary(
        path=path,
        name=path.name,
        library_id="custom",
        wav_count=_count_wavs(path),
        playable_wav_count=_count_playable(path),
        sample_format=_sample_format(path),
        midi_root=midi_root,
        midi_count=_count_midi(midi_root),
        library_type=lib_type,
    )
