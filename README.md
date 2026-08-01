# Drummer Studio

**Free, open-source drum studio software** for Windows.

Drummer Studio lets anyone play drum kits, browse MIDI grooves, and mix drums using sample libraries already installed on their computer (Toontrack EZDrummer, Cakewalk Drum Replacer, custom folders, and more).

No purchase required. No account required. MIT licensed — use, modify, and share freely.

## Features

- Clickable drum kit view (photo-based, EZdrummer-style)
- Groove browser with search and playback
- Mixer with channel faders and presets (Default, Roomy, Dry)
- Auto-detects Toontrack, Cakewalk, and custom library folders
- Reads standard WAV samples and MIDI files from disk

## Important: samples are not included

Drummer Studio is **application software only**. It does not ship with or redistribute any Toontrack, Cakewalk, or third-party drum samples.

You must **legally own and install** your own sample libraries. This project is not affiliated with or endorsed by Toontrack, BandLab/Cakewalk, or any other vendor.

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

## License

[MIT License](LICENSE) — free for personal and commercial use.

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Third-party libraries

Runtime dependencies (also open source):

- [pygame](https://www.pygame.org/) — audio playback
- [mido](https://mido.readthedocs.io/) — MIDI file reading
- [Pillow](https://python-pillow.org/) — kit image display
- [numpy](https://numpy.org/) — audio support
