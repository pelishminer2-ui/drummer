# Drummer Studio

**Free, open-source drum studio software** for Windows.

Drummer Studio is a standalone drum player with a visual kit, groove browser, and mixer. All sample libraries live under `Libraries/` next to the app — no external product names in the UI.

MIT licensed — use, modify, and share freely.

## Features

- Clickable drum kit view with photo-based hit zones
- Groove browser with search and playback
- Mixer with channel faders and presets (Default, Roomy, Dry)
- Self-contained `Libraries/` folder structure
- Reads standard WAV samples, SFZ kits, and MIDI grooves

## Important: samples are not included in the repo

The application does not ship with drum audio. Run `Import-Libraries.ps1` on your own machine to copy libraries you legally own into `F:\Drummer\Libraries` (or your install path).

## Quick start

### Run without installing

```text
Windows 11\Drummer Studio.exe
```

### Install (Desktop + Start Menu)

```powershell
.\Install Drummer Studio.ps1
```

### Import libraries (first-time setup)

```powershell
.\Import-Libraries.ps1
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

## Library layout

| Folder | Contents |
|--------|----------|
| `Libraries/Studio-Core` | Main WAV kit |
| `Libraries/Latin-Percussion` | Expansion kit + UI photos |
| `Libraries/Pack-Punk` | Punk rock one-shots + audio loops |
| `Libraries/Pack-SFZ` | SFZ drum kits |
| `Libraries/Grooves` | Main MIDI groove library |
| `Libraries/Grooves-Extended` | Additional MIDI grooves |
| `Libraries/Click-Sounds` | Metronome click WAVs |
| `Libraries/Grooves/User-Projects` | Your project MIDI |

## License

[MIT License](LICENSE) — free for personal and commercial use.

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
