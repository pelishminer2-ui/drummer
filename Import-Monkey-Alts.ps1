# Download Beta Monkey SoundCloud alt-rock loop demos into Libraries\Monkey-Alts
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Source = Join-Path $Root "source"

Write-Host "Monkey Alts — SoundCloud loop import" -ForegroundColor Cyan
Push-Location $Source
try {
    python monkey_alts_import.py
    if ($LASTEXITCODE -ne 0) { throw "monkey_alts_import.py failed" }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done. In Drummer Studio: Library -> Monkey Alts" -ForegroundColor Green
