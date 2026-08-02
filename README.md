# Drummer Studio

**Free, open-source drum studio software** for Windows — v**2.6.14**

Drummer Studio is a standalone drum player with a visual kit, groove browser, AI-powered match finder, and mixer. Sample libraries live under `Libraries/` next to the app.

MIT licensed — use, modify, and share freely.

## What it can do

### Play drums
- Photo-based clickable kit (Latin Percussion layout when that library is loaded)
- Keyboard triggers: Space kick, F snare, G/H hats, 1/2/3 toms, J ride
- Kit regions **flash in time** with MIDI groove playback

### Browse grooves & loops
- **Grooves** tab — MIDI grooves and audio loops from the selected library
- Search, double-click to play, export MIDI to WAV
- Libraries: Studio Core, Pack SFZ, Pack Punk, Latin Percussion, Monkey Alts, Metal Hitters, Cool Imports, and more

### Match your track to grooves (AI analysis)
Three ways to feed the matcher — use any or all:

| Button | What it does |
|--------|----------------|
| **Record Guitar** | Mic capture (4–30 sec), then analyze |
| **Import Track** | Pick WAV, MP3, FLAC, or OGG from disk |
| **Match Selected** | Use the highlighted row in Grooves, Ass Kickers, or Selected Tracks |

Analysis detects **BPM, key, rhythm feel**, and deep features (GPU when available). Results land on the **Matches Found** tab with match % scores. **Drag** a match into Audacity or another app.

Optional: **Open in Audacity** after recording.

### Other tabs
- **Ass Kickers** — imported SSD / genre demo MP3s; filter by genre; export WAV
- **Selected Tracks** — pin grooves from the active library + kit

### Mixer
- Per-channel level, pan, mute, solo
- Presets: Default, Roomy, Dry — **Apply Mix** updates the live kit

## Important: samples are not all included in the repo

The app does not ship with every drum library. Run import scripts on your machine for content you legally own or download.

| Script | Purpose |
|--------|---------|
| `Import-Libraries.ps1` | Copy owned kits/grooves into `Libraries/` |
| `Import-Monkey-Alts.ps1` | Download 14 alt-rock loop demos (SoundCloud) |
| `Import-Metal-Hitters.ps1` | Download 27 metal loop demos (SoundCloud) |
| `Import-Cool-Imports.ps1` | Import your WAV/MP3/MIDI into Cool Imports |
| `Import-SSD-Demos.ps1` | Fetch Ass Kickers demo tracks |

**Cannot import:** XLN Addictive Drums `.xpak` (locked plugin format). Export WAV from your DAW instead.

## Quick start

### Run without installing

```text
Windows 11\Drummer Studio.exe
```

### Install (Desktop + Start Menu)

```powershell
.\Install Drummer Studio.ps1
```

### Run from source

```powershell
cd source
pip install -r requirements.txt
python drummer_app.py
```

### Build executable

```powershell
cd source
pip install -r requirements.txt pyinstaller
.\build_installer.ps1
```

Output: `Windows 10\Drummer Studio.exe`, `Windows 11\Drummer Studio.exe`

## Library layout

| Folder | Contents |
|--------|----------|
| `Libraries/Studio-Core` | Main WAV kit |
| `Libraries/Latin-Percussion` | Expansion kit + UI photos |
| `Libraries/Pack-Punk` | Punk rock one-shots + audio loops |
| `Libraries/Pack-SFZ` | SFZ drum kits |
| `Libraries/Grooves` | Main MIDI groove library |
| `Libraries/Grooves-Extended` | Additional MIDI grooves |
| `Libraries/Monkey-Alts` | Alt-rock loop pack (run import script) |
| `Libraries/Metal-Hitters` | Metal loop pack (run import script) |
| `Libraries/Cool-Imports` | Your WAV/MP3/MIDI drop folder |
| `Libraries/Demo-Tracks` | Ass Kickers demos |
| `Libraries/User-Recordings` | Guitar takes for matching |
| `Libraries/Click-Sounds` | Metronome click WAVs |

See `Libraries/manifest.json` for the full registry.

## Release notes

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

[MIT License](LICENSE) — free for personal and commercial use.

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
