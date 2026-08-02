# Changelog

All notable changes to Drummer Studio are documented here.

## [2.6.17] — 2026-08-02

### Record count-in metronome
- **5-second built-in metronome** before mic capture (accent on beat 1)
- Ticks play through **pygame** (audible on Windows; same output as kit sounds)
- Count-in is **prepended to the saved WAV** as well as heard in speakers
- Groove playback stops before count-in begins

## [2.6.15] — 2026-08-02

### Groove playback fix
- MIDI preview no longer silent when mixer faders are down (Dry preset)
- Auto re-render at unity gain when faders would mute the groove

## [2.6.14] — 2026-08-02

### Match — record, import, or select any track
- **Record Guitar** — mic capture, then GPU/CPU analysis
- **Import Track** — WAV, MP3, FLAC, or OGG from disk
- **Match Selected** — analyze a loop or demo already in Grooves, Ass Kickers, or Selected Tracks
- Unified analysis pipeline; clearer status while recording or analyzing
- Find Matches blocks until analysis finishes (no more false “import first” errors)

### Other recent features (2.6.7–2.6.13)
- **Matches Found** tab — ranked results without replacing the Grooves browser
- **Drag matches** to Audacity or other apps (WAV/MIDI via drag cache)
- **Open in Audacity** after record (optional checkbox + manual button)
- **Kit play-along visuals** — drum pieces flash during groove playback
- **Monkey Alts** — 14 alt-rock loops (import script + local manifest)
- **Metal Hitters** — 27 metal loops (import script + local manifest)
- **Cool Imports** — user drop folder for WAV/MP3/MIDI (XLN `.xpak` not supported)
- **Ass Kickers** demo tab with genre filter and export
- **Selected Tracks** tab — pin grooves from the active library
- Background threads for record, analyze, and match search (UI stays responsive)
- Room reverb on mixer **Apply Mix** preset
- MT Wild Drums library entry (VST3 reference)

## [2.6.1] — 2026-08-01

- Smooth MIDI groove playback
- Library manifest sync

## [2.6.0] — initial open-source release

- Visual drum kit, groove browser, mixer
- SFZ kits, folder kits, MIDI grooves, audio loops
- Pack Punk, Pack SFZ, Studio Core, Latin Percussion support
