"""Parse SFZ instrument definitions for Pack SFZ libraries."""

from __future__ import annotations

import re
from dataclasses import dataclass
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

        for region_text in block.split("<region>")[1:]:
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
    samples = [
        SampleLayer(path=region.sample, velocity=(region.lovel + region.hivel) // 2, articulation="H")
        for region in regions
    ]
    return DrumPad(name=name, midi_notes=notes, samples=samples, label=label)


def list_sfz_kits(pack_root: Path, kit_defs: list[dict] | None = None) -> list[str]:
    if kit_defs:
        return [k.get("name", k.get("id", "")) for k in kit_defs if k.get("name") or k.get("id")]
    drums_dir = pack_root / "Drums"
    if not drums_dir.is_dir():
        return []
    kits: list[str] = []
    kicks = drums_dir / "Kicks"
    if kicks.is_dir():
        for sfz in sorted(kicks.glob("*.sfz")):
            kits.append(sfz.stem.replace(" Kick", ""))
    return kits


def _kit_prefix(pack_root: Path, kit_name: str, kit_defs: list[dict] | None) -> str:
    if kit_defs:
        for entry in kit_defs:
            if entry.get("name") == kit_name or entry.get("id") == kit_name:
                return entry.get("prefix", kit_name.replace(" ", ""))
    return kit_name.replace(" ", "")


def load_sfz_kit(pack_root: Path, kit_name: str, kit_defs: list[dict] | None = None) -> DrumKit:
    prefix = _kit_prefix(pack_root, kit_name, kit_defs)
    drums_dir = pack_root / "Drums"
    pads: dict[str, DrumPad] = {}

    sfz_files = [f for f in drums_dir.rglob("*.sfz") if prefix.lower() in f.stem.lower()]
    for sfz_path in sfz_files:
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
        pad = _regions_to_pad(pad_name, label, _parse_sfz(sfz_path))
        if pad:
            pads[pad_name] = pad

    return DrumKit(name=kit_name, root=pack_root, pads=pads)
