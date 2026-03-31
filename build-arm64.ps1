#
# Open WIC - Windows ARM64 Build Script
# ========================================
# Dieses Script baut die komplette Open WIC App als .exe für Windows ARM64.
#
# Was es tut (Schritt für Schritt):
#   1. Python 3.11 via winget installieren (falls nicht vorhanden)
#   2. Node.js 20 LTS via winget installieren (falls nicht vorhanden)
#   3. Python venv erstellen + Dependencies installieren
#   4. libusb 1.0.27 ARM64 DLL herunterladen & extrahieren
#   5. Python-Server mit PyInstaller zu open-wic-server.exe bündeln
#   6. libusb-1.0.dll neben die .exe kopieren
#   7. Electron-App bauen (React + Electron für ARM64)
#   8. Alles in release/ Ordner ablegen
#
# Voraussetzungen:
#   - winget (App Installer) vorhanden
#   - 7-Zip installiert unter C:\Program Files\7-Zip
#   - Internet-Verbindung
#

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$CoreDir = Join-Path $Root "core"
$InterfaceDir = Join-Path $Root "interface"
$BuildDir = Join-Path $Root "build-tmp"
$7zip = "C:\Program Files\7-Zip\7z.exe"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Open WIC - ARM64 Build" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# ─────────────────────────────────────────────
# Schritt 1: Python installieren
# ─────────────────────────────────────────────
Write-Host "[1/8] Python pruefen..." -ForegroundColor Yellow

$pythonInstalled = $false
try {
    $pyVer = & python --version 2>&1
    if ($pyVer -match "Python 3\.(1[1-9]|[2-9]\d)") {
        Write-Host "  -> Python bereits installiert: $pyVer" -ForegroundColor Green
        $pythonInstalled = $true
    }
} catch {}

if (-not $pythonInstalled) {
    Write-Host "  -> Python nicht gefunden. Installiere Python 3.11 via winget..." -ForegroundColor Yellow
    Write-Host "  -> ACHTUNG: UAC-Popup moeglich. Bitte bestaetigen." -ForegroundColor Red
    winget install Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    
    # PATH aktualisieren (winget fügt Python zum PATH hinzu, aber aktuelle Shell kennt es noch nicht)
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    
    # Verify
    $pyVer = & python --version 2>&1
    Write-Host "  -> Installiert: $pyVer" -ForegroundColor Green
}

# ─────────────────────────────────────────────
# Schritt 2: Node.js installieren
# ─────────────────────────────────────────────
Write-Host "`n[2/8] Node.js pruefen..." -ForegroundColor Yellow

$nodeInstalled = $false
try {
    $nodeVer = & node --version 2>&1
    if ($nodeVer -match "v(1[8-9]|[2-9]\d)") {
        Write-Host "  -> Node.js bereits installiert: $nodeVer" -ForegroundColor Green
        $nodeInstalled = $true
    }
} catch {}

if (-not $nodeInstalled) {
    Write-Host "  -> Node.js nicht gefunden. Installiere Node.js 20 LTS via winget..." -ForegroundColor Yellow
    winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    
    $nodeVer = & node --version 2>&1
    Write-Host "  -> Installiert: $nodeVer" -ForegroundColor Green
}

# ─────────────────────────────────────────────
# Schritt 3: Python venv + Dependencies
# ─────────────────────────────────────────────
Write-Host "`n[3/8] Python venv erstellen & Dependencies installieren..." -ForegroundColor Yellow

$venvDir = Join-Path $CoreDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "  -> Erstelle venv..."
    python -m venv $venvDir
}

Write-Host "  -> Installiere Python-Pakete..."
& $venvPip install --upgrade pip
& $venvPip install fastapi uvicorn pysnmp pyusb pydantic pyinstaller
& $venvPip install "git+https://github.com/firehills/reinkpy.git"

Write-Host "  -> Python Dependencies installiert." -ForegroundColor Green

# ─────────────────────────────────────────────
# Schritt 4: libusb 1.0.27 ARM64 herunterladen
# ─────────────────────────────────────────────
Write-Host "`n[4/8] libusb 1.0.27 ARM64 herunterladen..." -ForegroundColor Yellow

if (-not (Test-Path $BuildDir)) { New-Item -ItemType Directory -Path $BuildDir | Out-Null }

$libusbArchive = Join-Path $BuildDir "libusb-1.0.27.7z"
$libusbDir = Join-Path $BuildDir "libusb"
$libusbDll = Join-Path $libusbDir "VS2022\Release\arm64\libusb-1.0.dll"

if (-not (Test-Path $libusbDll)) {
    Write-Host "  -> Lade libusb-1.0.27.7z herunter..."
    Invoke-WebRequest `
        -Uri "https://github.com/libusb/libusb/releases/download/v1.0.27/libusb-1.0.27.7z" `
        -OutFile $libusbArchive

    Write-Host "  -> Entpacke mit 7-Zip..."
    & $7zip x $libusbArchive -o"$libusbDir" -y | Out-Null
    
    if (-not (Test-Path $libusbDll)) {
        # Pfad kann variieren - suche die ARM64 DLL
        $found = Get-ChildItem -Path $libusbDir -Recurse -Filter "libusb-1.0.dll" | 
                 Where-Object { $_.FullName -match "arm64" } | 
                 Select-Object -First 1
        if ($found) {
            $libusbDll = $found.FullName
        } else {
            Write-Host "  -> FEHLER: ARM64 libusb-1.0.dll nicht gefunden!" -ForegroundColor Red
            Write-Host "  -> Inhalt des Archivs:" -ForegroundColor Red
            Get-ChildItem -Path $libusbDir -Recurse | ForEach-Object { Write-Host "     $_" }
            exit 1
        }
    }
}

Write-Host "  -> libusb ARM64 DLL gefunden: $libusbDll" -ForegroundColor Green

# ─────────────────────────────────────────────
# Schritt 5: Python-Server mit PyInstaller bündeln
# ─────────────────────────────────────────────
Write-Host "`n[5/8] Python-Server mit PyInstaller buendeln..." -ForegroundColor Yellow

$pyinstaller = Join-Path $venvDir "Scripts\pyinstaller.exe"

Push-Location $CoreDir
& $pyinstaller `
    --onefile `
    --name "open-wic-server" `
    --hidden-import "uvicorn.logging" `
    --hidden-import "uvicorn.loops.auto" `
    --hidden-import "uvicorn.protocols.http.auto" `
    --hidden-import "uvicorn.protocols.websockets.auto" `
    --hidden-import "uvicorn.lifespan.on" `
    --hidden-import "reinkpy" `
    --noconfirm `
    server.py
Pop-Location

$serverExe = Join-Path $CoreDir "dist\open-wic-server.exe"
if (-not (Test-Path $serverExe)) {
    Write-Host "  -> FEHLER: open-wic-server.exe wurde nicht erstellt!" -ForegroundColor Red
    exit 1
}

Write-Host "  -> open-wic-server.exe erstellt." -ForegroundColor Green

# ─────────────────────────────────────────────
# Schritt 6: libusb DLL neben Server-exe kopieren
# ─────────────────────────────────────────────
Write-Host "`n[6/8] libusb-1.0.dll neben Server-exe kopieren..." -ForegroundColor Yellow

Copy-Item $libusbDll -Destination (Join-Path $CoreDir "dist\libusb-1.0.dll") -Force
Write-Host "  -> libusb-1.0.dll kopiert." -ForegroundColor Green

# ─────────────────────────────────────────────
# Schritt 7: Server-exe in Electron resources kopieren
# ─────────────────────────────────────────────
Write-Host "`n[7/8] Server-exe in Electron-App einbetten..." -ForegroundColor Yellow

$electronResources = Join-Path $InterfaceDir "resources"
if (-not (Test-Path $electronResources)) { New-Item -ItemType Directory -Path $electronResources | Out-Null }

Copy-Item (Join-Path $CoreDir "dist\open-wic-server.exe") -Destination $electronResources -Force
Copy-Item (Join-Path $CoreDir "dist\libusb-1.0.dll") -Destination $electronResources -Force

Write-Host "  -> Server-exe + libusb in interface/resources/ kopiert." -ForegroundColor Green

# ─────────────────────────────────────────────
# Schritt 8: Electron-App bauen
# ─────────────────────────────────────────────
Write-Host "`n[8/8] Electron-App fuer ARM64 bauen..." -ForegroundColor Yellow

Push-Location $InterfaceDir

Write-Host "  -> npm install..."
npm install --legacy-peer-deps

Write-Host "  -> Vite + Electron build..."
npm run build
npm run build:electron

Write-Host "  -> electron-builder --win --arm64..."
npx electron-builder --win --arm64

Pop-Location

# ─────────────────────────────────────────────
# Fertig!
# ─────────────────────────────────────────────
Write-Host "`n========================================" -ForegroundColor Green
Write-Host " BUILD ERFOLGREICH!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Ausgabe-Dateien:" -ForegroundColor Cyan
Write-Host "  Installer:  interface\release\*.exe" -ForegroundColor White
Write-Host "  Server:     core\dist\open-wic-server.exe" -ForegroundColor White
Write-Host "  libusb:     core\dist\libusb-1.0.dll" -ForegroundColor White
Write-Host ""
Write-Host "HINWEIS: Fuer USB-Reset muss der Drucker-Treiber" -ForegroundColor Yellow
Write-Host "         mit Zadig auf WinUSB umgestellt werden." -ForegroundColor Yellow
Write-Host ""
