#!/usr/bin/env python3
"""Scan every MIDI groove under Libraries and report files that cannot play."""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))

from groove_render import parse_midi_events
from library_scanner import libraries_root, load_manifest
from midi_drum_map import classify_groove_midi, resolve_pad, should_ignore_note
from playback_kit import load_groove_playback_kit


@dataclass
class ScanResult:
    path: Path
    root: Path
    events: int = 0
    playable: int = 0
    ignored: int = 0
    unmapped: int = 0
    top_notes: list[int] = field(default_factory=list)
    error: str = ""


def _midi_roots() -> list[tuple[str, Path]]:
    lib = libraries_root()
    roots: list[tuple[str, Path]] = []
    seen: set[Path] = set()

    for entry in load_manifest().get("groove_roots", []):
        folder = entry.get("folder", "")
        if not folder:
            continue
        path = (lib / folder).resolve()
        if path.is_dir() and path not in seen:
            roots.append((entry.get("name", folder), path))
            seen.add(path)

    extras = load_manifest().get("extras", {})
    for label, key in (("User Grooves", "user_grooves"),):
        folder = extras.get(key)
        if not folder:
            continue
        path = (lib / folder).resolve()
        if path.is_dir() and path not in seen:
            roots.append((label, path))
            seen.add(path)

    if not roots:
        roots.append(("Libraries", lib.resolve()))
    return roots


def _iter_midi_files(roots: list[tuple[str, Path]]) -> list[tuple[str, Path, Path]]:
    """Return (root_label, root_path, midi_path) for every groove MIDI."""
    skip_dirs = {"demo-tracks", "click-sounds", "patterns-ptn", "user-exports", "user-recordings", "_staging"}
    files: list[tuple[str, Path, Path]] = []
    lib = libraries_root().resolve()

    for root_label, root_path in roots:
        for midi_path in sorted(root_path.rglob("*.mid")):
            rel_parts = {p.lower() for p in midi_path.relative_to(lib).parts}
            if rel_parts & skip_dirs:
                continue
            files.append((root_label, root_path, midi_path))

    return files


def scan_file(midi_path: Path, root: Path, kit) -> ScanResult:
    rel = midi_path.relative_to(root)
    result = ScanResult(path=rel, root=root)
    try:
        events = parse_midi_events(midi_path)
    except Exception as exc:
        result.error = f"parse: {exc}"
        return result

    result.events = len(events)
    if not events:
        result.error = "no note_on events"
        return result

    note_counts: Counter[int] = Counter()
    for _, note, _ in events:
        if should_ignore_note(note, groove_playback=True):
            result.ignored += 1
            continue
        pad = resolve_pad(kit, note, groove_playback=True)
        if pad:
            result.playable += 1
        else:
            result.unmapped += 1
            note_counts[note] += 1

    if result.playable == 0:
        result.top_notes = [n for n, _ in note_counts.most_common(8)]
        if result.unmapped == 0 and result.ignored == result.events:
            result.error = "all notes filtered (clicks/FX only)"
        elif result.unmapped > 0:
            result.error = f"no mapped drum hits ({result.unmapped} unmapped)"
        else:
            result.error = "no playable hits"

    return result


def main() -> int:
    kit, kit_lib, kit_name = load_groove_playback_kit()
    roots = _midi_roots()

    print(f"Groove playback kit: {kit_name} ({kit_lib})")
    print(f"Scan roots ({len(roots)}):")
    for name, path in roots:
        count = len(list(path.rglob("*.mid")))
        print(f"  {name}: {path} ({count} .mid)")

    all_results: list[ScanResult] = []
    unmapped_global: Counter[int] = Counter()
    midi_files = _iter_midi_files(roots)
    total = len(midi_files)

    for root_name, root_path, midi_path in midi_files:
        result = scan_file(midi_path, root_path, kit)
        all_results.append(result)
        if result.playable == 0 and result.top_notes:
            for note in result.top_notes:
                unmapped_global[note] += 1

    broken = [r for r in all_results if r.error]
    playable = total - len(broken)

    print()
    print(f"TOTAL scanned: {total}")
    print(f"Playable:      {playable}")
    print(f"Broken:        {len(broken)}")

    by_error: Counter[str] = Counter()
    for r in broken:
        kind = r.error.split("(")[0].strip() if r.error else "unknown"
        by_error[kind] += 1
    print("\nFailure kinds:")
    for kind, count in by_error.most_common():
        print(f"  {count:5d}  {kind}")

    if unmapped_global:
        print("\nTop unmapped notes in broken files:")
        for note, count in unmapped_global.most_common(20):
            print(f"  note {note:3d}: {count} files")

    print("\nSample broken files:")
    for r in broken[:25]:
        notes = ",".join(str(n) for n in r.top_notes) if r.top_notes else "-"
        print(f"  {r.root.name}/{r.path}  ev={r.events}  {r.error}  notes=[{notes}]")

    report = {
        "kit": f"{kit_name} ({kit_lib})",
        "total": total,
        "playable": playable,
        "broken": len(broken),
        "failure_kinds": dict(by_error),
        "top_unmapped_notes": dict(unmapped_global.most_common(30)),
        "broken_samples": [
            {
                "file": str(r.root.name / r.path),
                "events": r.events,
                "error": r.error,
                "notes": r.top_notes,
            }
            for r in broken[:100]
        ],
    }
    out = libraries_root().parent / "source" / "groove_scan_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report: {out}")
    return 0 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
