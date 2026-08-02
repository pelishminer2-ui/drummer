# Download Beta Monkey metal SoundCloud loops into Libraries\Metal-Hitters
$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "source"
Write-Host "Metal Hitters — SoundCloud loop import" -ForegroundColor Cyan
Push-Location $Source
try {
    python metal_hitters_import.py
    if ($LASTEXITCODE -ne 0) { throw "metal_hitters_import.py failed" }
}
finally {
    Pop-Location
}
Write-Host ""
Write-Host "Done. In Drummer Studio: Library -> Metal Hitters" -ForegroundColor Green
