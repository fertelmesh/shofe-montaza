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
Write-Host "[1/5] Skill kopiran u $dst"

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
    Write-Host "[2/5] Instaliram Python 3.12..."
    winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
    $py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
} else {
    Write-Host "[2/5] Python postoji ($py)"
}

# 3) ffmpeg
if (-not (Test-Cmd "ffmpeg")) {
    Write-Host "[3/5] Instaliram ffmpeg..."
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
} else {
    Write-Host "[3/5] ffmpeg postoji"
}

# 4) Python paketi (transkripcija itd.) iz requirements.txt
Write-Host "[4/5] Instaliram Python pakete (lokalna transkripcija)..."
& $py -m pip install --upgrade --quiet -r (Join-Path $dst "requirements.txt")

# 5) HTML grafika: Node.js LTS + HyperFrames (nije nuzno za montazu; bez toga video izade bez grafike)
if (-not (Test-Cmd "node")) {
    Write-Host "[5/5] Instaliram Node.js LTS (za HTML grafiku)..."
    winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
} else {
    Write-Host "[5/5] Node.js postoji"
}
& $py (Join-Path $dst "scripts\grafika.py") instaliraj
if ($LASTEXITCODE -ne 0) {
    Write-Host "HTML grafika jos nije spremna (montaza radi i bez nje). Kasnije: python scripts\grafika.py instaliraj" -ForegroundColor Yellow
}

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
