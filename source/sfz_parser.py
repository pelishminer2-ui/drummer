"""Parse SFZ instrument definitions (Cakewalk Drum Replacer format)."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from library_parser import DrumKit, DrumPad, SampleLayer


@dataclass
class SfzRegion:
    sample: Path
    lovel: int = 0
    hivel: int = 127
    lorand: float = 0.0
    hirand: float = 1.0
    midi_note: int = 36


def _parse_sfz(path: Path) -> list[SfzRegion]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    base = path.parent
    regions: list[SfzRegion] = []
    current_note = 36

    for block in re.split(r"<group>", text)[1:]:
        note_match = re.search(r"group\s*=\s*(\d+)", block)
        if note_match:
            current_note = int(note_match.group(1))

        chunk = block.split("<region>")[1:]
        for region_text in chunk:
            sample_match = re.search(r"sample\s*=\s*(.+)", region_text)
            if not sample_match:
                continue
            rel = sample_match.group(1).strip()
            sample_path = (base / rel).resolve()
            if not sample_path.exists():
                continue

            def _num(name: str, default: float) -> float:
                m = re.search(rf"{name}\s*=\s*([\d.]+)", region_text)
                return float(m.group(1)) if m else default

            regions.append(
                SfzRegion(
                    sample=sample_path,
                    lovel=int(_num("lovel", 0)),
                    hivel=int(_num("hivel", 127)),
                    lorand=_num("lorand", 0.0),
                    hirand=_num("hirand", 1.0),
                    midi_note=current_note,
                )
            )
    return regions


def _regions_to_pad(name: str, label: str, regions: list[SfzRegion]) -> DrumPad | None:
    if not regions:
        return None
    notes = sorted(set(r.midi_note for r in regions))
    samples: list[SampleLayer] = []
    for region in regions:
        velocity = (region.lovel + region.hivel) // 2
        samples.append(
            SampleLayer(path=region.sample, velocity=velocity, articulation="H")
        )
    return DrumPad(name=name, midi_notes=notes, samples=samples, label=label)


def load_drum_replacer_kit(replacer_root: Path, kit_name: str) -> DrumKit:
    """Load a named Cakewalk Drum Replacer kit (Funktight, MetalHead, Roots, WholeLotta)."""
    drums_dir = replacer_root / "Drums"
    kit_key = kit_name.lower().replace(" ", "")
    pads: dict[str, DrumPad] = {}

    mappings = [
        (drums_dir / "Kicks" / f"{kit_name} Kick.sfz", "kick", "Kick"),
        (drums_dir / "Snares" / f"{kit_name} Snare.sfz", "snare", "Snare"),
        (drums_dir / "Toms" / "Hi Toms" / f"{kit_name} Hitoms.sfz", "tom_hi", "High Tom"),
        (drums_dir / "Toms" / "Lo Toms" / f"{kit_name} Lotoms.sfz", "tom_lo", "Low Tom"),
        (drums_dir / "Toms" / "Floor Toms" / f"{kit_name} Floortoms.sfz", "tom_floor", "Floor Tom"),
    ]

    # Filename spelling quirks in the install
    alt_names = {
        "Funktight": {"Hitoms": "Hitoms", "Lotoms": "Lotoms", "Floortoms": "Floortoms"},
        "MetalHead": {"Hitoms": "Hitoms", "Lotoms": "Lotoms", "Floortoms": "Floortoms"},
        "Roots": {"Hitoms": "Hitoms", "Lotoms": "Lotoms", "Floortoms": "Floortoms"},
        "WholeLotta": {"Hitoms": "Hitoms", "Lotoms": "Lotoms", "Floortoms": "Floortoms"},
    }

    sfz_files = list(drums_dir.rglob("*.sfz"))
    kit_sfz = [f for f in sfz_files if kit_name.lower() in f.stem.lower()]

    for sfz_path in kit_sfz:
        stem = sfz_path.stem.lower()
        if "kick" in stem:
            pad_name, label = "kick", "Kick"
        elif "snare" in stem:
            pad_name, label = "snare", "Snare"
        elif "hitom" in stem:
            pad_name, label = "tom_hi", "High Tom"
        elif "lotom" in stem:
            pad_name, label = "tom_lo", "Low Tom"
        elif "floor" in stem:
            pad_name, label = "tom_floor", "Floor Tom"
        else:
            continue
        regions = _parse_sfz(sfz_path)
        pad = _regions_to_pad(pad_name, label, regions)
        if pad:
            pads[pad_name] = pad

    return DrumKit(name=kit_name, root=replacer_root, pads=pads)


def list_drum_replacer_kits(replacer_root: Path) -> list[str]:
    kicks = replacer_root / "Drums" / "Kicks"
    if not kicks.is_dir():
        return []
    kits = []
    for sfz in sorted(kicks.glob("*.sfz")):
        name = sfz.stem.replace(" Kick", "")
        kits.append(name)
    return kits
