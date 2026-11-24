# Shofe montaža - instalacija za Windows
# Pokreni dvoklikom na INSTALIRAJ.bat (ili: powershell -ExecutionPolicy Bypass -File install.ps1)

$ErrorActionPreference = "Continue"
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$dst = Join-Path $env:USERPROFILE ".claude\skills\shofe-montaza"

Write-Host ""
Write-Host "=== Shofe montaza - instalacija ===" -ForegroundColor Yellow

# 1) Kopiraj skill tamo gdje ga Claude nalazi
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Get-ChildItem -Path $src -Exclude "INSTALIRAJ.bat" | Copy-Item -Destination $dst -Recurse -Force
Write-Host "[1/4] Skill kopiran u $dst"

function Test-Cmd($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# 2) Python (pazi na lazni 'python' iz Microsoft Storea)
$py = $null
foreach ($c in @("python", "py")) {
    if (Test-Cmd $c) {
        & $c --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $py = $c; break }
    }
}
if (-not $py) {
    Write-Host "[2/4] Instaliram Python 3.12..."
    winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
    $py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
} else {
    Write-Host "[2/4] Python postoji ($py)"
}

# 3) ffmpeg
if (-not (Test-Cmd "ffmpeg")) {
    Write-Host "[3/4] Instaliram ffmpeg..."
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
} else {
    Write-Host "[3/4] ffmpeg postoji"
}

# 4) Python paketi (transkripcija itd.) iz requirements.txt
Write-Host "[4/4] Instaliram Python pakete (lokalna transkripcija)..."
& $py -m pip install --upgrade --quiet -r (Join-Path $dst "requirements.txt")

Write-Host ""
& $py (Join-Path $dst "scripts\doctor.py")
$doctor = $LASTEXITCODE
Write-Host ""
if ($doctor -eq 0) {
    Write-Host "Gotovo. Zatvori i ponovno otvori Claude desktop, otvori Code u mapi s klipovima i napisi: montiraj ovo" -ForegroundColor Green
} else {
    Write-Host "Nesto nedostaje (vidi [!!] gore). Zatvori i ponovno otvori ovaj prozor pa pokreni INSTALIRAJ.bat jos jednom." -ForegroundColor Red
}
exit $doctor
