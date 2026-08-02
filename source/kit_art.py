"""Neutral kit photo — vendor branding removed, Drummer Studio only."""

from __future__ import annotations

from pathlib import Path

from kit_ui import KitVisual, _neutral_kit_regions


def _assets_dir() -> Path:
    return Path(__file__).resolve().parent / "assets"


def neutral_kit_path() -> Path:
    import sys

    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "assets" / "kit_studio.png"
        if bundled.exists():
            return bundled
    return _assets_dir() / "kit_studio.png"


def _sample_patch_color(img, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    from PIL import ImageStat

    crop = img.crop(box)
    stat = ImageStat.Stat(crop)
    return tuple(int(v) for v in stat.mean[:3])


def _draw_branding_masks(img) -> None:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    w, h = img.size

    # Top header — EZ logo strip
    header_color = _sample_patch_color(img, (0, 0, w, 8))
    draw.rectangle((0, 0, w, 92), fill=header_color)

    # Wood trim below header
    wood = _sample_patch_color(img, (40, 96, 120, 108))
    draw.rectangle((0, 92, w, 112), fill=wood)

    # Bottom-left vendor tag
    frame = _sample_patch_color(img, (8, h - 8, 40, h - 2))
    draw.rectangle((0, h - 36, 148, h), fill=frame)

    # Top-right piano / logo corner
    corner = _sample_patch_color(img, (w - 40, 8, w - 4, 40))
    draw.rectangle((w - 210, 0, w, 118), fill=corner)

    # Cymbal stamp (ride area)
    cym = _sample_patch_color(img, (560, 40, 610, 80))
    draw.ellipse((548, 22, 668, 142), fill=cym)

    # Subtle studio title — no vendor names
    draw.rectangle((w // 2 - 92, 18, w // 2 + 92, 52), fill=(32, 32, 38))
    try:
        from PIL import ImageFont

        font = ImageFont.truetype("segoeui.ttf", 20)
    except OSError:
        font = None
    draw.text((w // 2, 34), "Drummer Studio", fill=(235, 235, 240), anchor="mm", font=font)


def build_neutral_kit_image(force: bool = False) -> Path:
    """Build or refresh the neutral kit image."""
    out = neutral_kit_path()
    if out.exists() and not force:
        return out

    from PIL import Image

    out.parent.mkdir(parents=True, exist_ok=True)
    lib_root = Path(__file__).resolve().parent.parent / "Libraries" / "Latin-Percussion"
    source = lib_root / "bmp00128.png"
    if not source.exists():
        source = lib_root / "bmp00136.png"

    if source.exists():
        img = Image.open(source).convert("RGB")
        _draw_branding_masks(img)
    else:
        img = _generated_kit_image()

    img.save(out, "PNG", optimize=True)
    return out


def _generated_kit_image():
    from PIL import Image, ImageDraw

    w, h = 827, 483
    img = Image.new("RGB", (w, h), (26, 26, 32))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w, 110), fill=(58, 58, 66))
    draw.rectangle((0, h - 44, w, h), fill=(72, 48, 30))
    draw.rectangle((0, 110, w, h - 44), fill=(58, 18, 22))
    # kick
    draw.ellipse((330, 290, 470, 430), fill=(40, 38, 44), outline=(90, 88, 98))
    draw.ellipse((350, 310, 450, 410), fill=(210, 210, 215))
    # snare
    draw.ellipse((360, 150, 500, 250), fill=(40, 38, 44), outline=(90, 88, 98))
    draw.ellipse((380, 165, 480, 235), fill=(210, 210, 215))
    # toms
    for cx, cy, r in [(260, 210, 46), (280, 90, 40), (560, 100, 44)]:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(40, 38, 44), outline=(90, 88, 98))
        draw.ellipse((cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10), fill=(210, 210, 215))
    # hats / ride
    draw.ellipse((90, 120, 210, 190), fill=(170, 140, 60), outline=(120, 100, 40))
    draw.ellipse((560, 40, 720, 170), fill=(170, 140, 60), outline=(120, 100, 40))
    draw.text((w // 2, 34), "Drummer Studio", fill=(235, 235, 240), anchor="mm")
    return img


def load_neutral_kit_visual(library_root: Path) -> KitVisual:
    """Kit photo + hit zones without vendor branding."""
    build_neutral_kit_image()
    image_path = neutral_kit_path()

    kitconf = Path(__file__).resolve().parent.parent / "Libraries" / "Latin-Percussion" / "kitconf"
    if not kitconf.exists():
        kitconf = library_root / "kitconf"
    regions = _neutral_kit_regions()

    width, height = 827, 483
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            width, height = img.size
    except OSError:
        pass

    return KitVisual(image_path=image_path, regions=regions, canvas_width=width, canvas_height=height)
