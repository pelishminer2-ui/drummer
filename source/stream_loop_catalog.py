"""Load SoundCloud loop demo libraries (Monkey Alts, Metal Hitters, etc.)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

STREAM_LOOP_TYPES = frozenset({"monkey_alts", "metal_hitters"})


@dataclass
class StreamLoopTrack:
    section_id: str
    section_heading: str
    index: int
    title: str
    path: Path
    genre: str = ""
    bpm: str = ""


class StreamLoopLibrary:
    def __init__(self) -> None:
        self.tracks: list[StreamLoopTrack] = []
        self.sections: list[dict] = []

    def load(self, root: Path) -> int:
        self.tracks.clear()
        self.sections.clear()
        manifest = root / "manifest.json"
        if not manifest.exists():
            loops = root / "Loops"
            if loops.is_dir():
                self._load_from_disk(loops)
            return len(self.tracks)

        data = json.loads(manifest.read_text(encoding="utf-8"))
        for section in data.get("sections", []):
            heading = section.get("heading", section.get("id", "Loops"))
            self.sections.append({"id": section.get("id"), "heading": heading})
            for track in section.get("tracks", []):
                rel = track.get("file")
                if not rel:
                    continue
                path = root / rel
                if not path.exists():
                    continue
                self.tracks.append(
                    StreamLoopTrack(
                        section_id=section.get("id", ""),
                        section_heading=heading,
                        index=int(track.get("index", 0)),
                        title=track.get("title", path.stem),
                        path=path,
                        genre=track.get("genre", ""),
                        bpm=str(track.get("bpm", "")),
                    )
                )
        return len(self.tracks)

    def _load_from_disk(self, loops: Path) -> None:
        for section_dir in sorted(loops.iterdir()):
            if not section_dir.is_dir():
                continue
            heading = section_dir.name.replace("-", " ").title()
            self.sections.append({"id": section_dir.name, "heading": heading})
            for idx, path in enumerate(sorted(section_dir.glob("*.*")), start=1):
                if path.suffix.lower() not in {".mp3", ".wav", ".ogg", ".m4a"}:
                    continue
                self.tracks.append(
                    StreamLoopTrack(
                        section_id=section_dir.name,
                        section_heading=heading,
                        index=idx,
                        title=path.stem,
                        path=path,
                    )
                )

    def filter(self, query: str) -> list[StreamLoopTrack]:
        q = query.strip().lower()
        if not q:
            return self.tracks
        return [
            t
            for t in self.tracks
            if q in t.title.lower()
            or q in t.section_heading.lower()
            or q in t.genre.lower()
            or q in t.bpm
        ]

    def to_audio_loops(self) -> list:
        from audio_loops import AudioLoopInfo

        return [
            AudioLoopInfo(
                path=t.path,
                name=t.title,
                bpm=t.bpm,
                genre=t.genre or "Loop",
                pack=t.section_heading,
            )
            for t in self.tracks
        ]


# Back-compat alias
MonkeyAltsLibrary = StreamLoopLibrary
