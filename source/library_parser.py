"""Parse Toontrack EZDrummer kit configs and WAV sample libraries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SampleLayer:
    path: Path
    velocity: int
    articulation: str


@dataclass
class DrumPad:
    name: str
    midi_notes: list[int] = field(default_factory=list)
    samples: list[SampleLayer] = field(default_factory=list)
    label: str = ""
    layer_with: str = ""  # optional secondary pad triggered together (e.g. snare bottom)


@dataclass
class DrumKit:
    name: str
    root: Path
    pads: dict[str, DrumPad] = field(default_factory=dict)
    sample_rate: int = 44100


def discover_libraries(base_path: Path) -> list[Path]:
    found: list[Path] = []
    if not base_path.exists():
        return found

    sounds = base_path / "Sounds"
    if sounds.is_dir() and any(sounds.iterdir()):
        found.append(base_path)

    skip = {"helpmenu", "midi", "source", "build", "dist", "__pycache__"}
    for child in sorted(base_path.iterdir()):
        if not child.is_dir() or child.name.lower() in skip:
            continue
        child_sounds = child / "Sounds"
        if child_sounds.is_dir() and any(child_sounds.glob("**/*.wav")):
            found.append(child)

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in found:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _parse_padconf(path: Path) -> tuple[dict[str, list[int]], dict[str, dict]]:
    note_map: dict[str, list[int]] = {}
    pad_info: dict[str, dict] = {}
    if not path.exists():
        return note_map, pad_info

    text = path.read_text(encoding="utf-8", errors="ignore")
    for block in re.split(r"\bpad\s*\{", text)[1:]:
        name_match = re.search(r"name\s+(\S+)", block)
        key_match = re.search(r"key\s+(\d+)", block)
        if not name_match or not key_match:
            continue
        name = name_match.group(1)
        key = int(key_match.group(1))
        knee_match = re.search(r"velocityknee\s+H\s+(\d+)\s+L\s+(\d+)", block)
        pad_info[name] = {
            "key": key,
            "knee_high": int(knee_match.group(1)) if knee_match else 127,
            "knee_low": int(knee_match.group(2)) if knee_match else 1,
        }
        note_map.setdefault(name, []).append(key)

    for line in text.splitlines():
        alias_match = re.match(r"alias\s+(\S+)\s+(.+)", line.strip())
        if alias_match:
            pad_name = alias_match.group(1)
            notes = [int(n) for n in alias_match.group(2).split() if n.isdigit()]
            note_map.setdefault(pad_name, []).extend(notes)

    for name, notes in note_map.items():
        note_map[name] = sorted(set(notes))
    return note_map, pad_info


def _parse_uberconf(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict]]:
    drumsets: dict[str, dict[str, str]] = {}
    positions: dict[str, dict] = {}
    if not path.exists():
        return drumsets, positions

    text = path.read_text(encoding="utf-8", errors="ignore")
    drumset_block = re.search(r"drumsets\s*\{(.*)\}", text, re.DOTALL)
    if drumset_block:
        current: str | None = None
        for line in drumset_block.group(1).splitlines():
            kit_match = re.match(r'"([^"]+)"\s*\{', line.strip())
            if kit_match:
                current = kit_match.group(1)
                drumsets[current] = {}
                continue
            if current and line.strip() == "}":
                current = None
                continue
            if current:
                parts = line.strip().split()
                if len(parts) >= 2:
                    drumsets[current][parts[0].strip('"')] = parts[1]

    pos_block = re.search(r"positions\s*\{(.*)\}\s*\n\s*drumsets", text, re.DOTALL)
    if not pos_block:
        pos_block = re.search(r"positions\s*\{(.*)\}", text, re.DOTALL)
    if pos_block:
        current_name: str | None = None
        current_lines: list[str] = []
        depth = 0
        for line in pos_block.group(1).splitlines():
            header = re.match(r'\s*"?(.*?)"?\s+\d+\s*\{', line)
            if header and depth == 0:
                if current_name and current_lines:
                    positions[current_name] = _parse_position_block("\n".join(current_lines))
                current_name = header.group(1).strip()
                current_lines = []
                depth = 1
                continue
            if current_name:
                current_lines.append(line)
                depth += line.count("{") - line.count("}")
                if depth <= 0:
                    positions[current_name] = _parse_position_block("\n".join(current_lines))
                    current_name = None
                    current_lines = []
                    depth = 0

    return drumsets, positions


def _parse_position_block(block: str) -> dict:
    close_match = re.search(r"close\s+(\S+)", block)
    folder = close_match.group(1) if close_match else ""
    instruments: dict[str, str] = {}
    for line in block.splitlines():
        inst_match = re.match(r'\s*(\S+)\s+([A-Z]{2}\d+)\s+"', line)
        if inst_match:
            instruments[inst_match.group(1)] = inst_match.group(2)

    pads: dict[str, str] = {}
    pad_section = re.search(r"pads\s*\{(.*?)\}", block, re.DOTALL)
    if pad_section:
        for line in pad_section.group(1).splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                pads[parts[0]] = parts[1]
    return {"folder": folder, "instruments": instruments, "pads": pads}


def _resolve_position(positions: dict[str, dict], piece_name: str) -> dict | None:
    if piece_name in positions:
        return positions[piece_name]
    for key, value in positions.items():
        if key.replace('"', "").startswith(piece_name):
            return value
    return None


def _parse_wav_name(filename: str) -> tuple[str, int] | None:
    match = re.match(r".+_([HS])(\d+)\.wav$", filename, re.IGNORECASE)
    if not match:
        return None
    articulation = match.group(1).upper()
    layer_num = int(match.group(2))
    velocity_hint = layer_num * 8 if articulation == "S" else 64 + layer_num * 4
    return articulation, velocity_hint


def _collect_samples(folder: Path, token: str, instrument: str) -> list[SampleLayer]:
    if not folder.is_dir():
        return []
    layers: list[SampleLayer] = []
    pattern = re.compile(rf"^{re.escape(instrument)}_.*_{re.escape(token)}_", re.IGNORECASE)
    for wav in sorted(folder.glob("*.wav")):
        if not pattern.search(wav.name):
            continue
        parsed = _parse_wav_name(wav.name)
        if not parsed:
            continue
        articulation, velocity_hint = parsed
        layers.append(SampleLayer(path=wav, velocity=velocity_hint, articulation=articulation))
    layers.sort(key=lambda s: (s.articulation, s.velocity))
    return layers


def _collect_samples_prefix(folder: Path, instrument: str, token: str) -> list[SampleLayer]:
    if not folder.is_dir():
        return []
    layers: list[SampleLayer] = []
    pattern = re.compile(rf"^{re.escape(instrument)}_.*_{re.escape(token)}_", re.IGNORECASE)
    for wav in sorted(folder.glob("*.wav")):
        if not pattern.search(wav.name):
            continue
        parsed = _parse_wav_name(wav.name)
        if not parsed:
            continue
        articulation, velocity_hint = parsed
        layers.append(SampleLayer(path=wav, velocity=velocity_hint, articulation=articulation))
    layers.sort(key=lambda s: (s.articulation, s.velocity))
    return layers


CORE_GM_NOTES: dict[str, list[int]] = {
    "kickR": [36, 35, 34],
    "snareR": [38, 39, 40, 37],
    "snareBottom": [],
    "hatsCL": [42, 44, 62, 63, 61],
    "hatsO1": [46],
    "hatsO2": [45],
    "tom1L": [48, 74],
    "tom2L": [45, 43],
    "tom4L": [41],
    "ride4": [51, 59, 49],
    "crash1": [49, 57],
    "crash2": [52, 55],
}


def _load_core_ezdrummer_kit(sounds_dir: Path) -> dict[str, DrumPad]:
    """Build the default EZDrummer 2 core kit from Sounds/ folders."""
    pieces = [
        ("kickR", "Kick", "KD50", "FH_R", "Kick"),
        ("snareR", "SnareTop", "SD51", "FH_R", "Snare"),
        ("snareBottom", "SnareBottom", "KD50", "FH_R", "Snare Bottom"),
        ("hatsCL", "Hats", "HA50", "CL_R", "Closed Hat"),
        ("hatsO1", "Hats", "HA50", "O1_R", "Open Hat"),
        ("tom1L", "Tom1", "TO50_01", "FH_L", "Tom 1"),
        ("tom2L", "Tom2", "TO50_02", "FH_L", "Tom 2"),
        ("tom4L", "Tom4", "TO50_04", "FH_L", "Tom 4"),
        ("ride4", "OH", "RI50_04", "RD_R", "Ride"),
        ("crash1", "OH", "CR50_02", "CR_R", "Crash"),
        ("crash2", "OH", "CR51_02", "CR_R", "Crash 2"),
    ]
    pads: dict[str, DrumPad] = {}
    for pad_name, folder_name, instrument, token, label in pieces:
        folder = sounds_dir / folder_name
        samples = _collect_samples_prefix(folder, instrument, token)
        if not samples:
            continue
        pad = DrumPad(
            name=pad_name,
            midi_notes=CORE_GM_NOTES.get(pad_name, []),
            samples=samples,
            label=label,
        )
        if pad_name == "snareR":
            pad.layer_with = "snareBottom"
        pads[pad_name] = pad
    return pads


def _fallback_gm_pads(sounds_dir: Path) -> dict[str, DrumPad]:
    core = _load_core_ezdrummer_kit(sounds_dir)
    if core:
        return core
    folder_map = {
        "Kick": (36, "Kick"),
        "Snare": (38, "Snare"),
        "SnareTop": (38, "Snare"),
        "Hats": (42, "Hi-Hat"),
        "Tom1": (48, "Tom 1"),
        "Tom2": (45, "Tom 2"),
        "Tom4": (41, "Tom 4"),
        "OH": (49, "Crash"),
    }
    pads: dict[str, DrumPad] = {}
    for folder_name, (note, label) in folder_map.items():
        folder = sounds_dir / folder_name
        if not folder.is_dir():
            continue
        wavs = sorted(folder.glob("*.wav"))[:16]
        if not wavs:
            continue
        samples = [
            SampleLayer(path=wav, velocity=min(127, 20 + i * 8), articulation="H")
            for i, wav in enumerate(wavs)
        ]
        pads[folder_name.lower()] = DrumPad(
            name=folder_name.lower(), midi_notes=[note], samples=samples, label=label
        )
    return pads


def load_kit(library_root: Path, kit_name: str | None = None) -> DrumKit:
    library_root = library_root.resolve()
    padconf = library_root / "GM-padconf"
    uberconf = library_root / "uberconf"
    sounds_dir = library_root / "Sounds"

    note_map, pad_info = _parse_padconf(padconf)
    drumsets, positions = _parse_uberconf(uberconf)

    if not drumsets:
        pads = _fallback_gm_pads(sounds_dir)
        kit_label = "Default Core Kit" if (library_root / "Sounds").is_dir() else library_root.name
        return DrumKit(name=kit_label, root=library_root, pads=pads)

    chosen = kit_name if kit_name in drumsets else next(iter(drumsets))
    pads: dict[str, DrumPad] = {}
    for piece_name, instrument_key in drumsets[chosen].items():
        position = _resolve_position(positions, piece_name)
        if not position:
            continue
        folder = sounds_dir / position["folder"]
        instrument_code = position["instruments"].get(instrument_key, "")
        if not instrument_code:
            continue
        for pad_name, token in position["pads"].items():
            if token.lower() == "none":
                continue
            samples = _collect_samples(folder, token, instrument_code)
            if not samples:
                continue
            notes = note_map.get(pad_name, [])
            if not notes and pad_name in pad_info:
                notes = [pad_info[pad_name]["key"]]
            pads[pad_name] = DrumPad(name=pad_name, midi_notes=notes, samples=samples, label=pad_name)

    return DrumKit(name=chosen, root=library_root, pads=pads)


def list_drumsets(library_root: Path) -> list[str]:
    drumsets, _ = _parse_uberconf(library_root / "uberconf")
    if drumsets:
        return list(drumsets.keys())
    sounds = library_root / "Sounds"
    if sounds.is_dir() and any(sounds.glob("**/*.wav")):
        return ["Default Core Kit"]
    return [library_root.name]
