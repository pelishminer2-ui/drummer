# Download Steven Slate Drums public demo MP3s into F:\Drummer\Libraries\Demo-Tracks.
# Safe to re-run — skips files that are already downloaded.

$ErrorActionPreference = "Stop"
$Root = "F:\Drummer"
$Dest = Join-Path $Root "Libraries\Demo-Tracks"

Write-Host "Drummer Studio — SSD demo import" -ForegroundColor Cyan
Write-Host "Source: https://stevenslatedrums.com/" -ForegroundColor DarkGray
Write-Host "Target: $Dest`n" -ForegroundColor DarkGray

python (Join-Path $Root "source\ssd_demo_import.py") $Dest
if ($LASTEXITCODE -ne 0) { throw "ssd_demo_import.py failed ($LASTEXITCODE)" }

$count = (Get-ChildItem $Dest -Recurse -Filter "*.mp3" -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "`nDone — $count demo MP3 files in Demo-Tracks" -ForegroundColor Green
Write-Host "Includes SSD genres, Trigger demos, and BFD Metal Essentials (SoundCloud)." -ForegroundColor DarkGray
Write-Host "Open Drummer Studio and use the Ass Kickers tab — filter Genre: Metal for both metal tracks." -ForegroundColor Cyan
