# Import drum content into Libraries\ using neutral folder names only.
# Safe to re-run — robocopy skips unchanged files.
#
# By default this targets the "Libraries" folder next to this script.
# Pass -LibRoot to point at a different drive/location, e.g.:
#   .\Import-Libraries.ps1 -LibRoot "F:\Drummer\Libraries"
param(
    [string]$LibRoot = (Join-Path $PSScriptRoot "Libraries")
)

$ErrorActionPreference = "Stop"

$Sources = @{
    EzCore      = "C:\Program Files (x86)\Toontrack\EZDrummer\Sounds"
    EzStats     = "C:\Program Files (x86)\Toontrack\EZDrummer\Sounds\soundstats"
    EzLatin     = "C:\Program Files (x86)\Toontrack\EZDrummer\EZX_Cocktail"
    EzMidi      = "C:\Program Files (x86)\Toontrack\EZDrummer\Midi"
    CwReplacer  = "C:\Cakewalk Content\Drum Replacer"
    CwMidi      = "C:\Cakewalk Content\MIDI Library"
    CwMetronome = "C:\Cakewalk Content\Cakewalk Core\Metronome"
    CwPtnDrums  = "C:\Cakewalk Content\Cakewalk Core\PTN MIDI Patterns\Drums"
    CwProjects  = "C:\Cakewalk Projects"
    CwContent   = "C:\Cakewalk Content"
}

$Dest = @{
    StudioCore   = Join-Path $LibRoot "Studio-Core"
    Latin        = Join-Path $LibRoot "Latin-Percussion"
    Grooves      = Join-Path $LibRoot "Grooves"
    PackSfz      = Join-Path $LibRoot "Pack-SFZ"
    GroovesExt   = Join-Path $LibRoot "Grooves-Extended"
    ClickSounds  = Join-Path $LibRoot "Click-Sounds"
    PatternsPtn  = Join-Path $LibRoot "Patterns-PTN"
    UserProjects = Join-Path $LibRoot "Grooves\User-Projects"
}

function Copy-Tree {
    param([string]$Src, [string]$Dst)
    if (-not (Test-Path $Src)) {
        Write-Host "SKIP (missing): $Src" -ForegroundColor Yellow
        return $false
    }
    New-Item -ItemType Directory -Force -Path $Dst | Out-Null
    robocopy $Src $Dst /E /NFL /NDL /NJH /NJS /nc /ns /np /R:2 /W:2 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE): $Src -> $Dst" }
    Write-Host "OK: $Dst" -ForegroundColor Green
    return $true
}

Write-Host "Drummer Studio - library import" -ForegroundColor Cyan
Write-Host "Target: $LibRoot`n"

# Studio Core
if (Test-Path $Sources.EzCore) {
    Copy-Tree $Sources.EzCore (Join-Path $Dest.StudioCore "Sounds") | Out-Null
    if (Test-Path $Sources.EzStats) {
        Copy-Item $Sources.EzStats (Join-Path $Dest.StudioCore "soundstats") -Force
        Write-Host "OK: Studio-Core/soundstats" -ForegroundColor Green
    }
}

# Latin Percussion
if (Test-Path $Sources.EzLatin) {
    Copy-Tree $Sources.EzLatin $Dest.Latin | Out-Null
}

# Main grooves (neutral folder names)
if (Test-Path $Sources.EzMidi) {
    New-Item -ItemType Directory -Force -Path $Dest.Grooves | Out-Null
    $midiMap = [ordered]@{
        "01@EZD_POP#ROCK"    = "Pop-Rock"
        "04@EZX_COCKTAIL"    = "Latin-Grooves"
        "02@EZD_DEMOS"       = "Demos"
        "20@_USER_LIBRARIES" = "User"
        "MY MIDIFILES"       = "User-Files"
    }
    foreach ($key in $midiMap.Keys) {
        $src = Join-Path $Sources.EzMidi $key
        $dst = Join-Path $Dest.Grooves $midiMap[$key]
        if (Test-Path $src) { Copy-Tree $src $dst | Out-Null }
    }
    Get-ChildItem $Sources.EzMidi -Directory | ForEach-Object {
        if ($midiMap.Contains($_.Name)) { return }
        $dst = Join-Path $Dest.Grooves $_.Name
        if (-not (Test-Path $dst)) { Copy-Tree $_.FullName $dst | Out-Null }
    }
}

# SFZ pack with neutral kit prefixes
if (Test-Path $Sources.CwReplacer) {
    Copy-Tree $Sources.CwReplacer $Dest.PackSfz | Out-Null
    $sfzRenames = @{
        "Funktight"  = "FunkTight"
        "MetalHead"  = "MetalForge"
        "Roots"      = "RootsGroove"
        "WholeLotta" = "ClassicRock"
    }
    Get-ChildItem $Dest.PackSfz -Recurse -Filter "*.sfz" | ForEach-Object {
        $text = Get-Content $_.FullName -Raw -Encoding UTF8
        $newName = $_.Name
        foreach ($pair in $sfzRenames.GetEnumerator()) {
            $text = $text -replace [regex]::Escape($pair.Key), $pair.Value
            $newName = $newName -replace [regex]::Escape($pair.Key), $pair.Value
        }
        Set-Content -Path $_.FullName -Value $text -Encoding UTF8 -NoNewline
        if ($newName -ne $_.Name) {
            Rename-Item -LiteralPath $_.FullName -NewName $newName -ErrorAction SilentlyContinue
        }
    }
    Get-ChildItem $Dest.PackSfz -Recurse -Filter "*.wav" | ForEach-Object {
        $newName = $_.Name
        foreach ($pair in $sfzRenames.GetEnumerator()) {
            $newName = $newName -replace [regex]::Escape($pair.Key), $pair.Value
        }
        if ($newName -ne $_.Name) {
            Rename-Item -LiteralPath $_.FullName -NewName $newName -ErrorAction SilentlyContinue
        }
    }
}

# Extended grooves
if (Test-Path $Sources.CwMidi) {
    New-Item -ItemType Directory -Force -Path $Dest.GroovesExt | Out-Null
    $extMap = [ordered]@{
        "Groove Monkee" = "Groove-Collection"
        "SmartLoops"    = "Fills"
        "Drums"         = "Loops"
        "Bass"          = "Bass-Lines"
    }
    foreach ($key in $extMap.Keys) {
        $src = Join-Path $Sources.CwMidi $key
        $dst = Join-Path $Dest.GroovesExt $extMap[$key]
        if (Test-Path $src) { Copy-Tree $src $dst | Out-Null }
    }
}

# Metronome / click samples
if (Test-Path $Sources.CwMetronome) {
    Copy-Tree $Sources.CwMetronome $Dest.ClickSounds | Out-Null
}

# PTN drum patterns (stored for future decoder — not playable yet)
if (Test-Path $Sources.CwPtnDrums) {
    Copy-Tree $Sources.CwPtnDrums $Dest.PatternsPtn | Out-Null
}

# C:\Cakewalk Projects — user project folder + shortcut target scan
New-Item -ItemType Directory -Force -Path $Dest.UserProjects | Out-Null

function Import-UserMedia {
    param([string]$Root, [string]$Label)
    if (-not (Test-Path $Root)) { return }
    $wav = Get-ChildItem $Root -Recurse -Filter "*.wav" -File -ErrorAction SilentlyContinue
    $mid = Get-ChildItem $Root -Recurse -Filter "*.mid" -File -ErrorAction SilentlyContinue
    if ($wav.Count -eq 0 -and $mid.Count -eq 0) {
        Write-Host "SKIP (no wav/mid): $Label" -ForegroundColor Yellow
        return
    }
    foreach ($f in $mid) {
        $rel = $f.FullName.Substring($Root.Length).TrimStart("\")
        $target = Join-Path $Dest.UserProjects $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Copy-Item $f.FullName $target -Force
    }
    foreach ($f in $wav) {
        $rel = $f.FullName.Substring($Root.Length).TrimStart("\")
        $target = Join-Path (Join-Path $LibRoot "User-Samples") $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Copy-Item $f.FullName $target -Force
    }
    Write-Host "OK: imported user media from $Label" -ForegroundColor Green
}

Import-UserMedia $Sources.CwProjects "Cakewalk Projects"

# Follow shortcut in Cakewalk Projects if it points elsewhere with user files
Get-ChildItem $Sources.CwProjects -Filter "*.lnk*" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $sh = New-Object -ComObject WScript.Shell
        $target = $sh.CreateShortcut($_.FullName).TargetPath
        if ($target -and (Test-Path $target) -and $target -ne $Sources.CwContent) {
            Import-UserMedia $target "shortcut -> $target"
        }
    } catch {}
}

# Beta Monkey Punk pack (RAR archives) — edit $BetaMonkey below if yours
# lives somewhere other than a "Beta Monkey Drum Werks X - Punk" folder
# next to this script, e.g. "D:\Beta Monkey Drum Werks X - Punk".
$BetaMonkey = Join-Path $PSScriptRoot "Beta Monkey Drum Werks X - Punk"
$PunkDest = Join-Path $LibRoot "Pack-Punk"
$7z = "C:\Program Files\7-Zip\7z.exe"

function Import-PunkArchive {
    param([string]$RarPath, [string]$Kind)
    if (-not (Test-Path $RarPath)) { return }
    if (-not (Test-Path $7z)) {
        Write-Host "SKIP punk (7-Zip missing): $RarPath" -ForegroundColor Yellow
        return
    }
    $staging = Join-Path $LibRoot "_staging\punk-$([guid]::NewGuid().ToString('N').Substring(0,8))"
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    & $7z x $RarPath "-o$staging" -y | Out-Null
    if ($LASTEXITCODE -gt 1) {
        Write-Host "WARN: extract issue $RarPath" -ForegroundColor Yellow
    }
    Get-ChildItem $staging -Recurse -Filter "*.wav" -File | ForEach-Object {
        if ($Kind -eq "hits") {
            $parent = Split-Path $_.DirectoryName -Leaf
            if ($parent -eq "Cymbals") {
                $target = Join-Path $PunkDest "Sounds\Cymbals\$($_.Name)"
            } else {
                $target = Join-Path $PunkDest "Sounds\Drums\$($_.Name)"
            }
        } elseif ($Kind -eq "oneshots") {
            $target = Join-Path $PunkDest "Sounds\One-Shots\$($_.Name)"
        } else {
            $bpm = "Other"
            if ($RarPath -match "(\d{2,3})\s*BPM") { $bpm = $Matches[1] }
            elseif ($RarPath -match "In-Between") { $bpm = "In-Between" }
            $target = Join-Path $PunkDest "Loops\$bpm\$($_.Name)"
        }
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item $_.FullName $target -Force
    }
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
}

if (Test-Path $BetaMonkey) {
    Write-Host "`nImporting Pack Punk from $BetaMonkey" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Join-Path $PunkDest "Sounds") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $PunkDest "Loops") | Out-Null
    Get-ChildItem $BetaMonkey -Filter "*.rar" | ForEach-Object {
        $kind = "loops"
        if ($_.Name -match "Single Hit|One Shots") {
            $kind = if ($_.Name -match "One Shots") { "oneshots" } else { "hits" }
        }
        Write-Host "Extract: $($_.Name)" -ForegroundColor DarkGray
        Import-PunkArchive $_.FullName $kind
    }
    $wav = (Get-ChildItem $PunkDest -Recurse -Filter "*.wav" -EA SilentlyContinue | Measure-Object).Count
    Write-Host "OK: Pack-Punk ($wav wav files)" -ForegroundColor Green
}

Write-Host "`nImport finished: $LibRoot" -ForegroundColor Cyan
