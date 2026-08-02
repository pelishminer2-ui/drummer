"""Load drum kits from folder-based WAV one-shot libraries."""

from __future__ import annotations

import re
from pathlib import Path

from library_parser import DrumKit, DrumPad, SampleLayer


def _pad_for_file(path: Path) -> tuple[str, str] | None:
    name = path.stem.lower()
    if "kick" in name and "hh" not in name:
        return "kickR", "Kick"
    if "snare" in name:
        return "snareR", "Snare"
    if name.startswith("hh_") or name.startswith("hh ") or "_hh_" in name:
        return "hatsCL", "Hi-Hat"
    if "ohh" in name:
        return "hatsO1", "Open Hat"
    if "crash" in name or name.startswith("ccrash"):
        return "crash1", "Crash"
    if "ride" in name or name.startswith("rc_"):
        return "ride4", "Ride"
    if "tom" in name or "floor" in name:
        if "16" in name or "floor" in name:
            return "tom1R", "Floor Tom"
        return "tom1L", "Tom"
    if "fill" in name:
        return None
    return None


def _velocity_from_name(stem: str) -> int:
    match = re.search(r"_(\d{2})$", stem)
    if match:
        n = int(match.group(1))
        return min(127, max(20, n * 4 + 40))
    return 90


def load_folder_kit(library_root: Path, kit_name: str = "Standard Kit") -> DrumKit:
    library_root = library_root.resolve()
    sounds = library_root / "Sounds"
    if not sounds.is_dir():
        sounds = library_root

    pad_samples: dict[str, list[SampleLayer]] = {}
    pad_labels: dict[str, str] = {}
    gm_notes = {
        "kickR": [36],
        "snareR": [38],
        "hatsCL": [42],
        "hatsO1": [46],
        "crash1": [49],
        "ride4": [51],
        "tom1L": [48],
        "tom1R": [41],
    }

    for wav in sorted(sounds.rglob("*.wav")):
        if "__NI_" in str(wav):
            continue
        mapped = _pad_for_file(wav)
        if not mapped:
            continue
        pad_name, label = mapped
        pad_labels[pad_name] = label
        pad_samples.setdefault(pad_name, []).append(
            SampleLayer(path=wav, velocity=_velocity_from_name(wav.stem), articulation="H")
        )

    pads: dict[str, DrumPad] = {}
    for pad_name, samples in pad_samples.items():
        samples.sort(key=lambda s: s.velocity)
        pads[pad_name] = DrumPad(
            name=pad_name,
            midi_notes=gm_notes.get(pad_name, [36]),
            samples=samples,
            label=pad_labels.get(pad_name, pad_name),
        )

    return DrumKit(name=kit_name, root=library_root, pads=pads)


def list_folder_kits(library_root: Path) -> list[str]:
    p = load_folder_kit(library_root)
    if p.pads:
        return ["Punk Kit"]
    return ["Standard Kit"]
