# Contributing to Drummer Studio

Thank you for helping make free drum software available to everyone.

## How to contribute

1. Fork or clone the repository
2. Create a branch for your change
3. Make focused edits with clear commit messages
4. Test locally: `python source/drummer_app.py`
5. Open a pull request describing what changed and why

## Development setup

```powershell
cd source
pip install -r requirements.txt
python drummer_app.py
```

## Guidelines

- Keep the project free and open source (MIT license)
- Do not commit proprietary sample libraries or licensed audio content
- Do not add code that bypasses third-party DRM or license checks
- Match existing code style and keep changes focused
- Document new library formats in `Libraries/manifest.json` when possible

## Ideas welcome

- Additional library format support
- Better groove browser (BPM sync, loop)
- Linux and macOS builds
- Accessibility improvements
- Translations
