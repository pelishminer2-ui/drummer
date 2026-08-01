"""Parse kit UI layout and mixer configs from Toontrack-style libraries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Drum piece on kit photo -> sampler pad name(s)
PIECE_TO_PADS: dict[str, list[str]] = {
    "Kick": ["kickR", "kick"],
    "Snare": ["snareR", "snare"],
    "Snare2": ["hsnareR"],
    "Tom": ["tom1L", "tom1R", "tom_hi", "tom_lo", "tom_floor"],
    "Hats": ["hatsCL", "hatsO1", "hatsPL"],
    "Ride": ["ride4", "ride4BL", "ride4PU"],
}

PAD_TO_PIECE: dict[str, str] = {}
for piece, pads in PIECE_TO_PADS.items():
    for pad in pads:
        PAD_TO_PIECE[pad] = piece

PAD_ALIASES_ENGINE: dict[str, list[str]] = {
    "kickR": ["kick"],
    "snareR": ["snare"],
    "tom1L": ["tom_hi"],
    "tom1R": ["tom_lo", "tom_floor"],
    "hsnareR": ["tom_floor"],
}


@dataclass
class KitRegion:
    piece: str
    x: int
    y: int
    width: int
    height: int
    pads: list[str] = field(default_factory=list)


@dataclass
class KitVisual:
    image_path: Path | None
    regions: list[KitRegion] = field(default_factory=list)
    canvas_width: int = 827
    canvas_height: int = 483


@dataclass
class MixerChannel:
    name: str
    label: str
    volume: float = 1.0
    pan: float = 0.5


@dataclass
class MixerPreset:
    name: str
    channels: dict[str, MixerChannel] = field(default_factory=dict)


def find_kit_assets(library_root: Path) -> tuple[Path | None, Path | None]:
    """Return (kit_image, kitconf) if present."""
    root = library_root.resolve()
    if (root / "Sounds").is_dir() and root.name != "EZX_Cocktail":
        # Core library — check parent EZX or use generic
        parent = root.parent
        for candidate in [root, parent / "EZX_Cocktail"]:
            if (candidate / "kitconf").exists():
                root = candidate
                break

    kitconf = root / "kitconf"
    image = None
    for name in ("bmp00128.png", "bmp00136.png", "kit.png"):
        candidate = root / name
        if candidate.exists():
            image = candidate
            break
    if not kitconf.exists():
        kitconf = None
    return image, kitconf


def parse_kitconf(path: Path) -> list[KitRegion]:
    regions: list[KitRegion] = []
    if not path.exists():
        return regions

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r'"([^"]+)"\s+((?:-?\d+\s+)+)', line.strip())
        if not match:
            continue
        piece = match.group(1)
        nums = [int(n) for n in match.group(2).split()]
        if len(nums) < 8:
            continue
        # hit rectangle is typically the second group of 4 coords
        x, y, w, h = nums[4], nums[5], nums[6], nums[7]
        if w <= 0 or h <= 0:
            continue
        pads = PIECE_TO_PADS.get(piece, [])
        regions.append(KitRegion(piece=piece, x=x, y=y, width=w, height=h, pads=pads))
    return regions


def load_kit_visual(library_root: Path) -> KitVisual:
    image_path, kitconf_path = find_kit_assets(library_root)
    regions: list[KitRegion] = []
    if kitconf_path:
        regions = parse_kitconf(kitconf_path)

    if not regions:
        regions = _default_regions()

    width, height = 827, 483
    if image_path and image_path.exists():
        try:
            from PIL import Image

            with Image.open(image_path) as img:
                width, height = img.size
        except OSError:
            pass

    return KitVisual(image_path=image_path, regions=regions, canvas_width=width, canvas_height=height)


def _default_regions() -> list[KitRegion]:
    """Fallback click zones when no kitconf exists."""
    return [
        KitRegion("Kick", 340, 300, 120, 80, ["kickR", "kick"]),
        KitRegion("Snare", 300, 180, 100, 70, ["snareR", "snare"]),
        KitRegion("Hats", 120, 140, 90, 60, ["hatsCL", "hatsO1"]),
        KitRegion("Tom", 220, 200, 80, 60, ["tom1L", "tom_hi"]),
        KitRegion("Snare2", 400, 120, 70, 50, ["tom1R", "tom_lo", "hsnareR"]),
        KitRegion("Ride", 580, 120, 100, 80, ["ride4"]),
    ]


def parse_micconf(path: Path) -> tuple[list[MixerChannel], dict[str, MixerPreset]]:
    channels: dict[str, MixerChannel] = {}
    presets: dict[str, MixerPreset] = {}

    if not path.exists():
        return _default_mixer()

    text = path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"IF\s+0.*?FI", "", text, flags=re.DOTALL)

    for block in re.split(r"\bmic\s+(?:auto\s+)?\{", text)[1:]:
        name_match = re.search(r"name\s+(\S+)", block)
        mix_match = re.search(r'mixname\s+"([^"]+)"', block)
        vol_match = re.search(r"volume\s+([\d.]+)", block)
        pan_match = re.search(r"pan\s+([\d.]+)", block)
        if not name_match or name_match.group(1) == "dummy":
            continue
        name = name_match.group(1)
        label = mix_match.group(1) if mix_match else name[:4].upper()
        channels[name] = MixerChannel(
            name=name,
            label=label,
            volume=float(vol_match.group(1)) if vol_match else 1.0,
            pan=float(pan_match.group(1)) if pan_match else 0.5,
        )

    mixes_block = re.search(r"mixes\s*\{(.*)\}\s*$", text, re.DOTALL)
    if mixes_block:
        depth = 0
        current_preset: str | None = None
        current_piece: str | None = None
        for line in mixes_block.group(1).splitlines():
            stripped = line.strip()
            preset_match = re.match(r"(\w+)\s*\{", stripped)
            if preset_match and depth == 0:
                current_preset = preset_match.group(1)
                presets[current_preset] = MixerPreset(name=current_preset)
                depth = 1
                continue
            piece_match = re.match(r"(\w+)\s*\{", stripped)
            if piece_match and current_preset and depth == 1:
                current_piece = piece_match.group(1)
                depth = 2
                continue
            if current_preset and current_piece and depth == 2:
                vol = re.search(r"volume\s+([\d.]+)", stripped)
                pan = re.search(r"pan\s+([\d.]+)", stripped)
                if vol or pan:
                    ch = presets[current_preset].channels.setdefault(
                        current_piece,
                        MixerChannel(name=current_piece, label=current_piece[:4].upper()),
                    )
                    if vol:
                        ch.volume = float(vol.group(1))
                    if pan:
                        ch.pan = float(pan.group(1))
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                current_preset = None
                current_piece = None
                depth = 0

    if not channels:
        channels = {c.name: c for c in _default_mixer()[0]}
    if not presets:
        presets = _default_mixer()[1]

    return list(channels.values()), presets


def _default_mixer() -> tuple[list[MixerChannel], dict[str, MixerPreset]]:
    names = [
        ("Kick", "KD"),
        ("Snare", "SD"),
        ("Snare2", "SD2"),
        ("Tom", "TOM"),
        ("Hats", "HH"),
        ("Oh", "OH"),
    ]
    channels = [MixerChannel(name=n, label=l, volume=1.0, pan=0.5) for n, l in names]
    default = MixerPreset(name="Default")
    for ch in channels:
        default.channels[ch.name] = MixerChannel(name=ch.name, label=ch.label, volume=1.0, pan=ch.pan)
    presets = {
        "Default": default,
        "Roomy": MixerPreset(
            name="Roomy",
            channels={n: MixerChannel(name=n, label=l, volume=0.85, pan=0.5) for n, l in names},
        ),
        "Dry": MixerPreset(
            name="Dry",
            channels={
                "Kick": MixerChannel("Kick", "KD", 1.2, 0.5),
                "Snare": MixerChannel("Snare", "SD", 1.3, 0.5),
                "Snare2": MixerChannel("Snare2", "SD2", 1.0, 0.5),
                "Tom": MixerChannel("Tom", "TOM", 1.0, 0.5),
                "Hats": MixerChannel("Hats", "HH", 0.7, 0.5),
                "Oh": MixerChannel("Oh", "OH", 0.4, 0.5),
            },
        ),
    }
    return channels, presets


def load_mixer(library_root: Path) -> tuple[list[MixerChannel], dict[str, MixerPreset]]:
    root = library_root.resolve()
    micconf = root / "micconf"
    if not micconf.exists() and (root.parent / "EZX_Cocktail" / "micconf").exists():
        micconf = root.parent / "EZX_Cocktail" / "micconf"
    return parse_micconf(micconf)
