"""Auto-detect drum libraries on disk and map official source metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from library_parser import discover_libraries


@dataclass
class DetectedLibrary:
    path: Path
    name: str
    source_id: str
    wav_count: int
    midi_root: Path | None
    midi_count: int
    library_type: str = "toontrack"  # toontrack | cakewalk_sfz


def _bundle_dir() -> Path:
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def load_catalog() -> dict:
    catalog_path = _bundle_dir() / "source_catalog.json"
    if catalog_path.exists():
        return json.loads(catalog_path.read_text(encoding="utf-8"))
    return {"sources": []}


def _count_wavs(root: Path) -> int:
    sounds = root / "Sounds"
    if sounds.is_dir():
        return sum(1 for _ in sounds.rglob("*.wav"))
    sampledata = root / "Sampledata"
    if sampledata.is_dir():
        return sum(1 for _ in sampledata.rglob("*.wav"))
    return sum(1 for _ in root.rglob("*.wav")) if root.is_dir() else 0


def _detect_cakewalk(cakewalk_root: Path, seen: set[Path]) -> list[DetectedLibrary]:
    found: list[DetectedLibrary] = []
    replacer = cakewalk_root / "Drum Replacer"
    if not replacer.is_dir():
        return found

    resolved = replacer.resolve()
    if resolved in seen:
        return found
    seen.add(resolved)

    midi_root = cakewalk_root / "MIDI Library"
    midi_count = len(list(midi_root.rglob("*.mid"))) if midi_root.is_dir() else 0
    wav_count = _count_wavs(replacer)

    found.append(
        DetectedLibrary(
            path=replacer,
            name="Cakewalk Drum Replacer",
            source_id="cakewalk_drums",
            wav_count=wav_count,
            midi_root=midi_root if midi_root.is_dir() else None,
            midi_count=midi_count,
            library_type="cakewalk_sfz",
        )
    )
    return found


def _find_midi_root(install_root: Path) -> Path | None:
    midi = install_root / "Midi"
    return midi if midi.is_dir() else None


def detect_all() -> list[DetectedLibrary]:
    catalog = load_catalog()
    found: list[DetectedLibrary] = []
    seen: set[Path] = set()

    for source in catalog.get("sources", []):
        for raw_path in source.get("scan_paths_windows", []):
            install_root = Path(raw_path)
            if not install_root.exists():
                continue

            if source.get("id") == "cakewalk":
                found.extend(_detect_cakewalk(install_root, seen))
                continue
            resolved = install_root.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            libs = discover_libraries(install_root)
            if not libs:
                if (install_root / "Sounds").is_dir():
                    libs = [install_root]
                else:
                    continue

            midi_root = _find_midi_root(install_root)
            midi_count = len(list(midi_root.rglob("*.mid"))) if midi_root else 0

            for lib in libs:
                found.append(
                    DetectedLibrary(
                        path=lib,
                        name=lib.name,
                        source_id=source["id"],
                        wav_count=_count_wavs(lib),
                        midi_root=midi_root,
                        midi_count=midi_count,
                    )
                )

    extra_roots = [
        Path(r"C:\Program Files (x86)\Toontrack"),
        Path(r"C:\Program Files\Toontrack"),
    ]
    for root in extra_roots:
        if not root.exists():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            resolved = child.resolve()
            if resolved in seen:
                continue
            libs = discover_libraries(child)
            if not libs:
                continue
            seen.add(resolved)
            midi_root = _find_midi_root(child)
            midi_count = len(list(midi_root.rglob("*.mid"))) if midi_root else 0
            for lib in libs:
                found.append(
                    DetectedLibrary(
                        path=lib,
                        name=lib.name,
                        source_id="local",
                        wav_count=_count_wavs(lib),
                        midi_root=midi_root,
                        midi_count=midi_count,
                    )
                )

    cakewalk_root = Path(r"C:\Cakewalk Content")
    if cakewalk_root.exists():
        found.extend(_detect_cakewalk(cakewalk_root, seen))

    return sorted(
        found,
        key=lambda item: ((item.path / "uberconf").exists(), item.wav_count),
        reverse=True,
    )
