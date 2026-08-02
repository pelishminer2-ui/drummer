#!/usr/bin/env python3
"""Import Beta Monkey SoundCloud playlists into Libraries/Monkey-Alts."""

from __future__ import annotations

import sys
from pathlib import Path

from soundcloud_loop_import import download_library

PLAYLISTS = [
    {
        "id": "drum-werks-xix",
        "heading": "Drum Werks XIX — Rock / Indie / Alt",
        "genre": "Alt Rock",
        "url": "https://soundcloud.com/betamonkey/sets/drum-werks-xix-rock-indie-alt-rock-drum-loops",
    },
    {
        "id": "drum-werks-xx",
        "heading": "Drum Werks XX — Loop Demos",
        "genre": "Rock",
        "url": "https://soundcloud.com/betamonkey/sets/drum-werks-xx-drum-loops-demos",
    },
]

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "Libraries" / "Monkey-Alts"
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    print(f"Monkey Alts import -> {root}")
    catalog = download_library(root, "Monkey Alts", PLAYLISTS)
    total = sum(len(s["tracks"]) for s in catalog["sections"])
    print(f"Done. {total} loops in {len(catalog['sections'])} playlists.")
