#!/usr/bin/env python3
"""Import Beta Monkey metal SoundCloud playlists into Libraries/Metal-Hitters."""

from __future__ import annotations

import sys
from pathlib import Path

from soundcloud_loop_import import download_library

PLAYLISTS = [
    {
        "id": "double-bass-mania-viii",
        "heading": "Double Bass Mania VIII — Metal Drum Loops",
        "genre": "Metal",
        "url": "https://soundcloud.com/betamonkey/sets/double-bass-mania-viii-metal-drum-loops",
    },
    {
        "id": "double-bass-mania-vii",
        "heading": "Double Bass Mania VII — Modern",
        "genre": "Metal",
        "url": "https://soundcloud.com/betamonkey/sets/double-bass-mania-vii-modern",
    },
]

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "Libraries" / "Metal-Hitters"
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    print(f"Metal Hitters import -> {root}")
    catalog = download_library(root, "Metal Hitters", PLAYLISTS)
    total = sum(len(s["tracks"]) for s in catalog["sections"])
    print(f"Done. {total} loops in {len(catalog['sections'])} playlists.")
