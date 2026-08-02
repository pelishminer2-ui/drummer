#!/usr/bin/env python3
"""Import WAV/MP3/MIDI into Libraries/Cool-Imports (standard formats only)."""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from library_scanner import libraries_root

AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
MIDI_EXT = {".mid", ".midi"}
SKIP_EXT = {".xpak", ".dll", ".exe", ".pdk", ".sfz"}

# Strip vendor branding from filenames when copying user-provided files.
_VENDOR_RE = re.compile(
    r"(?i)\b(xln|addictive[\s_-]?drums?|ad2|adpack|toontrack|ezdrummer|ez[\s_-]?drummer|"
    r"preview[\s_-]?|sound[\s_-]?data)\b|[\s_-]+"
)


def _sanitize_stem(stem: str) -> str:
    cleaned = _VENDOR_RE.sub(" ", stem).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "import"


def _unique_path(dest_dir: Path, stem: str, suffix: str) -> Path:
    candidate = dest_dir / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _classify(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in SKIP_EXT:
        return None
    if ext in MIDI_EXT:
        return "grooves"
    if ext in AUDIO_EXT:
        name = path.stem.lower()
        if "loop" in name or "groove" in name or path.parent.name.lower() == "loops":
            return "loops"
        return "kits"
    return None


def import_cool_imports(source: Path) -> dict[str, int]:
    root = libraries_root() / "Cool-Imports"
    dests = {
        "kits": root / "Kits",
        "loops": root / "Loops",
        "grooves": root / "Grooves",
    }
    for folder in dests.values():
        folder.mkdir(parents=True, exist_ok=True)

    counts = {"kits": 0, "loops": 0, "grooves": 0, "skipped": 0}
    if not source.is_dir():
        raise FileNotFoundError(f"Source folder not found: {source}")

    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in SKIP_EXT:
            counts["skipped"] += 1
            continue
        kind = _classify(path)
        if not kind:
            counts["skipped"] += 1
            continue
        stem = _sanitize_stem(path.stem)
        dest = _unique_path(dests[kind], stem, path.suffix.lower())
        shutil.copy2(path, dest)
        counts[kind] += 1

    return counts


def main() -> int:
    lib_root = libraries_root()
    default_inbox = lib_root / "Cool-Imports" / "Inbox"
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_inbox

    print(f"Cool Imports — scanning: {source}")
    if not source.is_dir():
        print(f"Missing folder: {source}")
        print("Usage: python cool_imports_import.py [source_folder]")
        print("  Default source: Libraries/Cool-Imports/Inbox")
        return 1

    try:
        counts = import_cool_imports(source)
    except OSError as exc:
        print(f"Import failed: {exc}")
        return 1

    print(
        f"Copied: {counts['kits']} kit WAVs, {counts['loops']} loops, "
        f"{counts['grooves']} MIDI grooves ({counts['skipped']} skipped)"
    )
    if counts["skipped"] and source.drive.lower() == "c:" and "xln" in str(source).lower():
        print()
        print("XLN .xpak files cannot be imported — export WAV/MIDI from your plugin first.")
    print(f"Library: {lib_root / 'Cool-Imports'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
