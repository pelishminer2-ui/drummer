# Convenience wrapper: download ALL Beta Monkey SoundCloud libraries locally
# (no online playback) by calling the individual import scripts, so the
# download logic only lives in one place each.
$ErrorActionPreference = "Stop"

Write-Host "Downloading stream loop libraries ..." -ForegroundColor Cyan

& (Join-Path $PSScriptRoot "Import-Monkey-Alts.ps1")
if ($LASTEXITCODE -ne 0) { throw "Import-Monkey-Alts.ps1 failed" }

& (Join-Path $PSScriptRoot "Import-Metal-Hitters.ps1")
if ($LASTEXITCODE -ne 0) { throw "Import-Metal-Hitters.ps1 failed" }

Write-Host ""
Write-Host "Local libraries ready:" -ForegroundColor Green
Write-Host "  Library -> Monkey Alts   (14 loops)"
Write-Host "  Library -> Metal Hitters (27 loops)"
Write-Host "Playback uses saved MP3 files only — no SoundCloud streaming."
