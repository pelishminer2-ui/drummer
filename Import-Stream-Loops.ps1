# Download ALL Beta Monkey SoundCloud libraries locally (no online playback).
$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "source"

Write-Host "Downloading stream loop libraries to F:\Drummer\Libraries ..." -ForegroundColor Cyan
Push-Location $Source
try {
    python monkey_alts_import.py
    if ($LASTEXITCODE -ne 0) { throw "monkey_alts_import failed" }
    python metal_hitters_import.py
    if ($LASTEXITCODE -ne 0) { throw "metal_hitters_import failed" }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Local libraries ready:" -ForegroundColor Green
Write-Host "  Library -> Monkey Alts   (14 loops)"
Write-Host "  Library -> Metal Hitters (27 loops)"
Write-Host "Playback uses saved MP3 files only — no SoundCloud streaming."
