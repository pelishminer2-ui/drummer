"""Discover and scan all MIDI grooves under Libraries."""

from __future__ import annotations

from pathlib import Path

from library_scanner import DetectedLibrary, libraries_root, load_manifest
from midi_grooves import GrooveInfo, GrooveLibrary


def _scan_roots(lib: GrooveLibrary, roots: list[Path]) -> None:
    seen = {g.path.resolve() for g in lib.grooves}
    for root in roots:
        if not root.is_dir():
            continue
        extra = GrooveLibrary()
        extra.scan(root)
        for groove in extra.grooves:
            key = groove.path.resolve()
            if key not in seen:
                lib.grooves.append(groove)
                seen.add(key)


def load_session_grooves(current: DetectedLibrary | None = None) -> list[GrooveInfo]:
    """MIDI grooves available while using any kit (including sample-only libraries like MT Wild)."""
    lib = GrooveLibrary()
    lib_root = libraries_root()
    manifest = load_manifest()
    roots: list[Path] = []

    for entry in manifest.get("groove_roots", []):
        folder = entry.get("folder")
        if folder:
            roots.append(lib_root / folder)

    extras = manifest.get("extras", {})
    user_grooves = extras.get("user_grooves")
    if user_grooves:
        roots.append(lib_root / user_grooves)

    if current and current.midi_root and current.midi_root.is_dir():
        roots.insert(0, current.midi_root)

    _scan_roots(lib, roots)

    if not lib.grooves and lib_root.is_dir():
        lib.scan(lib_root)

    lib.grooves.sort(key=lambda g: (g.pack.lower(), g.name.lower()))
    return lib.grooves


def scan_all_grooves() -> list[GrooveInfo]:
    """Every *.mid under F:\\Drummer\\Libraries (legacy helper)."""
    return load_session_grooves()
