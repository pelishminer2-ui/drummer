#!/usr/bin/env python3
"""Scan F:\\Drummer\\Libraries and rewrite manifest.json with live metadata."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from library_scanner import detect_all, libraries_root
from wav_io import count_playable_wavs, first_wav_format

SCHEMA_VERSION = "1.2.0"


def _app_version(source_dir: Path) -> str:
    text = (source_dir / "drummer_app.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def _count_midis(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("*.mid"))


def _count_files(root: Path, pattern: str) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob(pattern))


def _demo_track_count(lib_root: Path) -> int:
    demo = lib_root / "Demo-Tracks"
    if not demo.is_dir():
        return 0
    manifest = demo / "manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return sum(len(s.get("tracks", [])) for s in data.get("sections", []))
        except json.JSONDecodeError:
            pass
    return _count_files(demo, "*.mp3") + _count_files(demo, "*.wav")


def build_manifest(project_root: Path) -> dict:
    source_dir = project_root / "source"
    lib_root = libraries_root() if libraries_root().is_dir() else project_root / "Libraries"
    detected = detect_all()

    libraries_meta = []
    for lib in detected:
        entry: dict = {
            "id": lib.library_id,
            "name": lib.name,
            "folder": lib.path.name,
            "type": lib.library_type,
            "path": str(lib.path.relative_to(lib_root)).replace("\\", "/"),
            "exists": lib.path.is_dir(),
            "wav_count": lib.wav_count,
            "playable_wav_count": lib.playable_wav_count,
            "sample_format": lib.sample_format,
            "midi_count": lib.midi_count,
        }
        if lib.midi_root:
            entry["midi_folder"] = str(lib.midi_root.relative_to(lib_root)).replace("\\", "/")
        if lib.library_type == "sfz" and lib.sfz_kits:
            entry["kits"] = lib.sfz_kits
        if lib.kit_labels:
            entry["kit_labels"] = lib.kit_labels
        libraries_meta.append(entry)

    groove_roots = []
    for name, folder in (
        ("Main Grooves", "Grooves"),
        ("Extended Grooves", "Grooves-Extended"),
    ):
        path = lib_root / folder
        groove_roots.append(
            {
                "name": name,
                "folder": folder,
                "exists": path.is_dir(),
                "midi_count": _count_midis(path),
            }
        )

    extras = {
        "click_sounds": "Click-Sounds",
        "patterns_ptn": "Patterns-PTN",
        "user_samples": "User-Samples",
        "user_grooves": "Grooves/User-Projects",
        "demo_tracks": "Demo-Tracks",
        "user_exports": "User-Exports",
        "user_recordings": "User-Recordings",
    }
    extras_meta = {}
    for key, rel in extras.items():
        p = lib_root / rel
        extras_meta[key] = {
            "folder": rel,
            "exists": p.is_dir(),
            "files": _count_files(p, "*.*") if p.is_dir() else 0,
        }

    # Preserve editable manifest fields from existing file (pdk_file, loops_folder, etc.)
    manifest_path = lib_root / "manifest.json"
    preserved: dict[str, dict] = {}
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            for entry in old.get("libraries", []):
                preserved[entry.get("id", "")] = entry
        except json.JSONDecodeError:
            pass

    libraries_out = []
    for meta in libraries_meta:
        lib_id = meta["id"]
        base = preserved.get(lib_id, {})
        out = {
            "id": lib_id,
            "name": meta["name"],
            "folder": meta["folder"],
            "type": meta["type"],
        }
        for key in (
            "pdk_file",
            "default_kit",
            "midi_folder",
            "loops_folder",
            "kits",
            "kit_labels",
            "visual_from",
        ):
            if key in base:
                out[key] = base[key]
            elif key == "midi_folder" and meta.get("midi_folder"):
                out["midi_folder"] = meta["midi_folder"]
        out["_stats"] = {
            "wav_count": meta["wav_count"],
            "playable_wav_count": meta["playable_wav_count"],
            "sample_format": meta["sample_format"],
            "midi_count": meta["midi_count"],
            "exists": meta["exists"],
        }
        libraries_out.append(out)

    total_midi = sum(g["midi_count"] for g in groove_roots)
    demo_count = _demo_track_count(lib_root)

    return {
        "version": SCHEMA_VERSION,
        "app_version": _app_version(source_dir),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(lib_root.resolve()),
        "project_root": str(project_root.resolve()),
        "libraries": libraries_out,
        "groove_roots": [{"name": g["name"], "folder": g["folder"]} for g in groove_roots],
        "extras": {k: v["folder"] for k, v in extras_meta.items()},
        "inventory": {
            "libraries_detected": len(libraries_out),
            "total_midi_grooves": total_midi,
            "demo_tracks": demo_count,
            "groove_roots": groove_roots,
            "extras": extras_meta,
        },
    }


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    manifest = build_manifest(project_root)
    out_path = project_root / "Libraries" / "manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    inv = manifest["inventory"]
    print(f"Synced manifest -> {out_path}")
    print(f"  app_version: {manifest['app_version']}")
    print(f"  libraries:   {inv['libraries_detected']}")
    print(f"  MIDI grooves: {inv['total_midi_grooves']:,}")
    print(f"  Ass Kickers:  {inv['demo_tracks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
