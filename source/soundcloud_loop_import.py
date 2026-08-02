"""Shared SoundCloud loop import for Beta Monkey stream libraries."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def safe_filename(title: str, index: int) -> str:
    slug = re.sub(r"[^\w\s\-']", "", title).strip().lower()
    slug = re.sub(r"\s+", "-", slug)[:70] or f"track-{index}"
    return f"{index:02d}-{slug}.mp3"


def download_playlist(url: str, dest_dir: Path) -> list[dict]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(dest_dir / "tmp-%(playlist_index)02d.%(ext)s")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            "http_mp3_1_0/bestaudio[ext=mp3]/bestaudio",
            "--yes-playlist",
            "--write-info-json",
            "-o",
            out_template,
            url,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp playlist download failed")

    tracks: list[dict] = []
    for info_path in sorted(dest_dir.glob("tmp-*.info.json")):
        data = json.loads(info_path.read_text(encoding="utf-8"))
        idx = int(re.search(r"tmp-(\d+)", info_path.name).group(1))
        title = data.get("title") or data.get("track") or info_path.stem
        audio = info_path.with_suffix("")
        for ext in (".mp3", ".m4a", ".opus", ".ogg"):
            candidate = audio.with_suffix(ext)
            if candidate.exists():
                audio = candidate
                break
        if not audio.exists():
            continue
        final = dest_dir / safe_filename(title, idx)
        if audio != final:
            if final.exists():
                final.unlink()
            audio.rename(final)
        info_path.unlink(missing_ok=True)
        tracks.append({"index": idx, "title": title, "file": final.name})
    tracks.sort(key=lambda t: t["index"])
    for leftover in dest_dir.glob("tmp-*"):
        leftover.unlink(missing_ok=True)
    return tracks


def _guess_bpm(title: str) -> str:
    m = re.search(r"(\d{2,3})\s*bpm", title, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{2,3})\b", title)
    if m and 60 <= int(m.group(1)) <= 300:
        return m.group(1)
    return ""


def build_catalog(dest_root: Path, library_name: str, playlists: list[dict]) -> dict:
    sections = []
    for playlist in playlists:
        section_dir = dest_root / "Loops" / playlist["id"]
        print(f"Downloading {playlist['heading']} ...")
        tracks = download_playlist(playlist["url"], section_dir)
        section_tracks = []
        for track in tracks:
            rel = f"Loops/{playlist['id']}/{track['file']}"
            section_tracks.append(
                {
                    "index": track["index"],
                    "title": track["title"],
                    "file": rel.replace("\\", "/"),
                    "genre": playlist["genre"],
                    "bpm": _guess_bpm(track["title"]),
                    "source": playlist["url"],
                }
            )
        sections.append(
            {
                "id": playlist["id"],
                "heading": playlist["heading"],
                "tracks": section_tracks,
            }
        )
        print(f"  OK {len(section_tracks)} tracks")
    return {
        "source": "https://soundcloud.com/betamonkey",
        "library": library_name,
        "sections": sections,
    }


def download_library(dest_root: Path, library_name: str, playlists: list[dict]) -> dict:
    dest_root.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog(dest_root, library_name, playlists)
    (dest_root / "manifest.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog
