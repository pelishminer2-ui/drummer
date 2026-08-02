"""Fetch Steven Slate Drums public demo catalog from stevenslatedrums.com."""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

SOURCE_URL = "https://stevenslatedrums.com/"
CDN_PREFIX = "https://slateaudio.sfo2.cdn.digitaloceanspaces.com/drums-imgs/audio/"

BFD_METAL_DEMO = {
    "soundcloud_url": "https://soundcloud.com/bfddrums/modernity-drum-only",
    "title": "Metal Essentials",
    "subtitle": "Modernity Drum Only — BFD Player Expansion",
    "genre": "Metal",
    "source": "https://www.bfddrums.com/bfd-player-expansions/metal-essentials/",
}


def _fetch_homepage() -> str:
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "DrummerStudio/1.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


def _clean_url(url: str) -> str:
    url = html.unescape(url).replace("&#x27;", "'").replace("&amp;", "&")
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/:%")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _safe_filename(title: str, index: int) -> str:
    slug = re.sub(r"[^\w\s\-']", "", title).strip().lower()
    slug = re.sub(r"\s+", "-", slug)[:60]
    return f"{index:02d}-{slug}.mp3"


def parse_demo_catalog(page_html: str) -> dict:
    left = re.findall(
        r'"title":"((?:\\.|[^"\\])*)","genre":"[^"]*","audioTrack":"((?:\\.|[^"\\])*)"',
        page_html,
    )

    ssd: list[dict] = []
    trigger: list[dict] = []
    genres: list[dict] = []

    # Parse structured blocks by proximity to typename markers
    for block in re.finditer(
        r'PagesHomeBlocksPlaylistPairLeftTracks","title":"(?P<title>[^"]+)".*?"audioTrack":"(?P<url>[^"]+)"',
        page_html,
    ):
        ssd.append({"title": block.group("title"), "url": _clean_url(block.group("url"))})

    for block in re.finditer(
        r'PagesHomeBlocksPlaylistPairRightTracks","title":"(?P<title>[^"]+)".*?"audioTrack":"(?P<url>[^"]+)"',
        page_html,
    ):
        trigger.append({"title": block.group("title"), "url": _clean_url(block.group("url"))})

    for block in re.finditer(
        r'PagesHomeBlocksTracksPlayerTracks\\",\\"thumbnail\\":\\"[^"]*\\",\\"genre\\":\\"[^"]*\\",'
        r'\\"title\\":\\"(?P<title>[^"]*)\\",\\"subtitle\\":\\"(?P<subtitle>[^"]*)\\",\\"audioTrack\\":\\"(?P<url>[^"]*)\\"',
        page_html,
    ):
        subtitle = block.group("subtitle").encode("utf-8").decode("unicode_escape")
        genres.append(
            {
                "title": block.group("title"),
                "subtitle": subtitle,
                "url": _clean_url(block.group("url")),
            }
        )

    if not genres:
        genre_map = {
            "Rock": ("Add instant energy to your track", "Cutya - New Designer Kit.mp3"),
            "Metal": ("The heaviest drums on the planet", "Metal Man - New Designer Kit.mp3"),
            "Hip-Hop": ("Massive lows to make your track slap", "stevenslatedrums-fullmixdemos-trip-hop.mp3"),
            "Country": ("Soulful acoustic kits that work every time", "stevenslatedrums-solodrumdemos-nashville-fat-kit.mp3"),
            "Electronic": ("Build the perfect beat to get the crowd moving", "ssd-ex-dance-house.mp3"),
            "Pop": ("For drums that sit perfectly in your mix", "stevenslatedrums-solodrumdemos-classicpopkit.mp3"),
            "1970s": ("Warm, acoustic kits full of vintage vibe", "ssd-platinum-70s-classic-kit.mp3"),
            "Jazz": ("Organic hits & touches make mixes come alive", "Jazzy Jerry - New Designer Kit.mp3"),
        }
        for title, (subtitle, _fname) in genre_map.items():
            m = re.search(
                rf'(?:\\)?"title(?:\\)?":(?:\\)?"{re.escape(title)}(?:\\)?",'
                rf'(?:\\)?"subtitle(?:\\)?":(?:\\)?"{re.escape(subtitle)}(?:\\)?".*?'
                rf'(?:\\)?"audioTrack(?:\\)?":(?:\\)?"(?P<url>[^"\\]+)(?:\\)?"',
                page_html,
            )
            if m:
                genres.append({"title": title, "subtitle": subtitle, "url": _clean_url(m.group("url"))})

    # Deduplicate SSD/trigger by title
    def _dedupe(items: list[dict]) -> list[dict]:
        seen_t: set[str] = set()
        out: list[dict] = []
        for item in items:
            key = item["title"].lower()
            if key in seen_t:
                continue
            seen_t.add(key)
            out.append(item)
        return out

    ssd = _dedupe(ssd)
    trigger = _dedupe(trigger)
    genres = _dedupe(genres)

    if len(ssd) < 15:
        ssd = _dedupe(ssd + _fallback_from_urls(page_html, "SSD%20Full"))
    if len(trigger) < 8:
        trigger = _dedupe(trigger + _fallback_from_urls(page_html, "Trigger"))

    return {
        "source": SOURCE_URL,
        "sections": [
            {
                "id": "ssd-55",
                "heading": "Drummer SSD 5.5",
                "tracks": [{"index": i + 1, **t} for i, t in enumerate(ssd)],
            },
            {
                "id": "trigger-2",
                "heading": "Drummer Trigger 2 Before & After",
                "tracks": [{"index": i + 1, **t} for i, t in enumerate(trigger)],
            },
            {
                "id": "genres",
                "heading": "Drummer Genre Demos",
                "tracks": [
                    {
                        "index": i + 1,
                        "title": f"Drummer {t['title']}",
                        "subtitle": t.get("subtitle", ""),
                        "genre": t.get("genre", t["title"]),
                        "url": t["url"],
                    }
                    for i, t in enumerate(genres)
                ],
            },
        ],
    }


def _append_extra_genre_demos(catalog: dict) -> None:
    genres_sec = next((s for s in catalog["sections"] if s["id"] == "genres"), None)
    if not genres_sec:
        return
    tracks = genres_sec["tracks"]
    next_index = max((t.get("index", 0) for t in tracks), default=0) + 1
    extra = BFD_METAL_DEMO
    tracks.append(
        {
            "index": next_index,
            "title": f"Drummer {extra['title']}",
            "subtitle": extra["subtitle"],
            "genre": extra["genre"],
            "source": extra["source"],
            "soundcloud_url": extra["soundcloud_url"],
        }
    )


def _fallback_from_urls(page_html: str, kind: str) -> list[dict]:
    urls = re.findall(rf'({re.escape(CDN_PREFIX)}{kind}[^"\']+\.mp3)', page_html)
    out: list[dict] = []
    seen: set[str] = set()
    for url in urls:
        url = _clean_url(url)
        if url in seen:
            continue
        seen.add(url)
        name = Path(urllib.parse.unquote(url)).stem
        name = re.sub(r"^\d+\s+", "", name).replace("_", " ").replace("-", " ")
        out.append({"title": name, "url": url})
    return out


def _download_soundcloud(url: str, dest: Path) -> None:
    import subprocess
    import sys

    dest.parent.mkdir(parents=True, exist_ok=True)
    out_template = str(dest.with_suffix("")) + ".%(ext)s"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            "http_mp3_1_0/bestaudio[ext=mp3]/bestaudio",
            "--no-playlist",
            "-o",
            out_template,
            url,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp download failed")
    if not dest.exists():
        for candidate in dest.parent.glob(dest.stem + ".*"):
            if candidate.suffix.lower() in {".mp3", ".m4a", ".opus", ".ogg"}:
                if candidate != dest:
                    candidate.rename(dest)
                return
    if not dest.exists():
        raise RuntimeError(f"Download finished but file missing: {dest}")


def download_catalog(catalog: dict, dest_root: Path) -> dict:
    dest_root.mkdir(parents=True, exist_ok=True)
    for section in catalog["sections"]:
        section_dir = dest_root / section["id"]
        section_dir.mkdir(parents=True, exist_ok=True)
        for track in section["tracks"]:
            fname = _safe_filename(track["title"], track["index"])
            out = section_dir / fname
            track["file"] = str(out.relative_to(dest_root)).replace("\\", "/")
            if out.exists() and out.stat().st_size > 1000:
                continue
            if track.get("soundcloud_url"):
                _download_soundcloud(track["soundcloud_url"], out)
                continue
            url = track["url"]
            req = urllib.request.Request(url, headers={"User-Agent": "DrummerStudio/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                out.write_bytes(resp.read())
    manifest_path = dest_root / "manifest.json"
    manifest_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return catalog


def build_default_catalog() -> dict:
    page = _fetch_homepage()
    catalog = parse_demo_catalog(page)
    _append_extra_genre_demos(catalog)
    return catalog


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parent.parent / "Libraries" / "Demo-Tracks"
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    print(f"Fetching demos from {SOURCE_URL} ...")
    catalog = build_default_catalog()
    for sec in catalog["sections"]:
        print(sec["heading"], len(sec["tracks"]))
    print(f"Downloading to {root} ...")
    download_catalog(catalog, root)
    print("Done.")
