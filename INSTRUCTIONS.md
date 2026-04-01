# Open WIC — ARM64 Build & Development Notes

## Project Overview

Open WIC is an Epson printer waste ink counter (WIC) reset tool.
- **Backend**: Python/FastAPI server (`core/server.py`) — SNMP network scan + USB EEPROM read/reset via reinkpy
- **Frontend**: React/Vite + Electron desktop app (`interface/`)
- **Target**: Windows ARM64 native `.exe`

## Architecture

```
core/server.py          → FastAPI backend (port 8000)
  ├── SNMP scan         → pysnmp v7 (network printers)
  ├── USB scan          → reinkpy + libusb (local printers)
  └── EEPROM reset      → reinkpy (USB only)

interface/
  ├── src/App.tsx       → Main React UI
  ├── electron/main.ts  → Electron main process (spawns backend)
  └── build-electron.ts → esbuild config for Electron main
```

Electron launches `open-wic-server.exe` from `resources/backend/` via `extraResources`.

## Environment

| Component     | Version       | Notes |
|---------------|---------------|-------|
| OS            | Windows 10.0.26200 ARM64 | User: `seblh` |
| Python        | 3.11.9 ARM64  | `C:\Users\seblh\AppData\Local\Programs\Python\Python311-arm64\` |
| Node.js       | 24.14.1 ARM64 | via winget |
| Electron      | 41.0.2 ARM64  | electron-builder 26.8.1 |
| PyInstaller   | 6.19.0        | win_arm64 |
| libusb        | 1.0.29        | ARM64 DLL: `build-tmp/libusb29/MinGW-llvm-aarch64/dll/libusb-1.0.dll` |
| pysnmp        | 7.1.22        | **v7 API** — snake_case! |
| reinkpy       | from GitHub   | `pip install git+https://github.com/firehills/reinkpy.git` (NOT on PyPI!) |

- **venv**: `C:\dev\open-wic\core\venv\`
- **Git remotes**: `origin` = `bxddesign/open-wic`, `fork` = `sebllll/open-wic`

## Critical Technical Details

### pysnmp v7 API (breaking change vs v4/v5!)
```python
# v7 (current) — snake_case, async create
from pysnmp.hlapi.asyncio import get_cmd, UdpTransportTarget
target = await UdpTransportTarget.create((ip, 161), timeout=1.5, retries=0)
errInd, errStat, errIdx, varBinds = await get_cmd(engine, community, target, ctx, oid)

# v4/v5 (old) — camelCase, sync constructor — DO NOT USE
# getCmd(), UdpTransportTarget((ip, 161), timeout=1.5)
```

### Waste Ink Counter — EEPROM only, NOT SNMP
- The Epson private OID `1.3.6.1.4.1.1248.1.2.2.1.1.1.1.1` returns the **printer identity string** (MFG, MDL, SN), NOT the waste ink level
- Waste counter is stored in **EEPROM**, readable only via **USB + reinkpy**
- Wi-Fi printers return `wasteScore: -1` (unknown) — frontend shows "Unknown" + USB hint
- USB printers: reinkpy reads EEPROM addresses from its model database

### reinkpy API
```python
import reinkpy

# Find USB Epson printers
for udev in reinkpy.UsbDevice.ifind(manufacturer="EPSON"):
    model = udev.model
    serial = udev.serial_number
    
    # Configure for EEPROM access
    epson = udev.epson.configure(True)  # True = auto-detect model
    
    # Read waste counter addresses
    waste_mem = epson.spec.get_mem('waste counter')
    # waste_mem = {'desc': '...', 'addr': [addr1, addr2, ...], 'reset': [0, 0, ...]}
    
    vals = epson.read_eeprom(*waste_mem['addr'])
    # vals = [(addr, value), ...] — value is int or None
    
    # Reset waste counters
    epson.reset_waste()
```

### libusb on Windows
- Requires **WinUSB driver** — standard Windows printer driver does NOT work with libusb
- Use [Zadig](https://zadig.akeo.ie/) to switch driver if needed
- DLL must be in PATH or same directory as exe
- For dev: `core/libusb-1.0.dll` (copied from build-tmp)
- For production: Electron's `resources/backend/libusb-1.0.dll`

### Electron quirks
- `"type": "module"` in package.json → esbuild must output **CJS**: `format: 'cjs'`, `outfile: 'dist-electron/main.cjs'`
- `package.json` → `"main": "dist-electron/main.cjs"`
- Vite: `base: './'` for file:// (Electron loads from disk)
- Custom Vite plugin strips `crossorigin` attribute (breaks file:// + module scripts)
- `modulePreload: false` in vite.config.ts
- `webSecurity: false` in BrowserWindow (needed for file:// + fetch to localhost)
- Supabase client: conditional init (null when no env vars)
- Dev detection: `const isDev = !app.isPackaged` (NOT electron-is-dev)
- Backend detection: `fs.existsSync(serverExe)` (NOT isDev — unpacked builds are "not packaged")

## Build Commands

### 1. Backend (PyInstaller)
```powershell
cd C:\dev\open-wic\core
C:\dev\open-wic\core\venv\Scripts\pyinstaller.exe `
  --onefile --name "open-wic-server" `
  --add-binary "C:/dev/open-wic/core/venv/Lib/site-packages/pysnmp;pysnmp" `
  --add-data "C:/dev/open-wic/build-tmp/libusb29/MinGW-llvm-aarch64/dll/libusb-1.0.dll;." `
  --paths "C:/dev/open-wic/core/venv/Lib/site-packages" `
  --hidden-import pysnmp.hlapi.asyncio `
  --hidden-import pysnmp.hlapi `
  --hidden-import pysnmp.smi `
  --hidden-import pysnmp.smi.mibs `
  --hidden-import pysnmp.carrier.asyncio `
  --hidden-import pysnmp.carrier.asyncio.dgram.udp `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.protocols.http `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.http.h11_impl `
  --hidden-import uvicorn.protocols.websockets `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import uvicorn.lifespan `
  --hidden-import uvicorn.lifespan.on `
  --hidden-import reinkpy `
  --hidden-import reinkpy.epson `
  --hidden-import reinkpy.usb `
  --hidden-import reinkpy.d4 `
  --distpath core/dist --workpath core/build --specpath core `
  server.py
```

### 2. Copy to Electron resources
```powershell
Copy-Item "core/dist/open-wic-server.exe" -Destination "interface/resources/" -Force
Copy-Item "build-tmp/libusb29/MinGW-llvm-aarch64/dll/libusb-1.0.dll" -Destination "interface/resources/" -Force
```

### 3. Frontend (Vite + esbuild)
```powershell
cd interface
npm run build           # Vite → dist/
npm run build:electron  # esbuild → dist-electron/main.cjs
```

### 4. Electron installer
```powershell
cd interface
npx electron-builder --win --arm64
# Output: interface/release/Open WIC Setup 0.0.0.exe (~118 MB)
# Unpacked: interface/release/win-arm64-unpacked/
```

### Dev testing (without full rebuild)
```powershell
# Start backend directly
$env:PATH = "C:\dev\open-wic\core;" + $env:PATH  # for libusb DLL
cd core; & venv\Scripts\python.exe server.py

# Test scan
Invoke-WebRequest -Uri "http://127.0.0.1:8000/scan" -UseBasicParsing | Select-Object -ExpandProperty Content
```

## WIP State — Where to Continue

### What's done
- ✅ Full ARM64 build pipeline (Python + Node + Electron)
- ✅ SNMP network scan with pysnmp v7 (finds EPSON WF-3720 at 192.168.100.61)
- ✅ Scan optimized (104s → 3s via TCP:80 pre-filter)
- ✅ wasteScore = -1 for Wi-Fi printers (EEPROM not SNMP-readable)
- ✅ Frontend handles unknown state (grey bar, "Unknown", USB hint)
- ✅ USB scan code using reinkpy (reads EEPROM waste counter addresses)
- ✅ Reset endpoint uses reinkpy for USB printers

### What's WIP / TODO
1. **USB printer detection not working yet**
   - `libusb` finds 0 devices even with DLL loaded
   - Root cause: Windows uses its own printer driver, NOT WinUSB
   - **Fix**: Install [Zadig](https://zadig.akeo.ie/) → select the Epson USB device → replace driver with **WinUSB**
   - After Zadig, the printer won't work as a normal Windows printer anymore (only via libusb)
   - Alternative: Consider using **reinkpy's D4 protocol over network** instead of USB

2. **EEPROM waste counter calculation needs real-world testing**
   - Current code reads waste_mem addresses and computes `main_counter = byte0 + byte1 * 256`
   - Divides by 80 to get percentage (assuming ~8000 = 100%)
   - These values need validation against a real USB-connected printer
   - The WF-3720 may not be in reinkpy's model database → `configure(True)` might fail

3. **Rebuild needed after server.py changes**
   - server.py was updated to use reinkpy for USB scan (instead of raw pyusb)
   - Removed `import usb.core, usb.util` (now only reinkpy)
   - Need to rebuild: PyInstaller → copy to resources → Vite + esbuild → electron-builder

4. **Minor improvements**
   - Wi-Fi reset endpoint is still simulated (`asyncio.sleep(3)`) — should return error or disable
   - `webSecurity: false` should be addressed properly
   - `build-arm64.ps1` script needs updating to match all manual fixes
   - Consider adding manual IP entry in UI for printers not found via auto-scan

### Test printer
- **Model**: EPSON WF-3720 Series
- **Wi-Fi IP**: 192.168.100.61
- **SNMP hostname**: EPSONBC8D71
- **USB**: Not yet tested (cable needs to be connected + Zadig driver swap)

## Git History
```
c2539e3 fix: wasteScore -1 for Wi-Fi printers, UI shows 'Unknown' + USB hint
94dcba5 refactor: minimize diff vs upstream
7608961 fix: use pysnmp v7 API, optimize scan (104s → 3s)
bb7c49c Fix Pydantic model: string → str
820b9f3 Fix Electron production: optional supabase, remove crossorigin, detect backend
c73c16e Fix blank window: set Vite base to ./
60f2654 Remove electron-is-dev, use app.isPackaged
7f779f3 Fix ESM/CJS conflict: output Electron main as .cjs
4abdfc7 Embed backend in Electron
dd26695 ARM64 build: update script, .gitignore, supabase dep
e397a0f Add ARM64 build script for Windows
```

## File Map

| File | Purpose |
|------|---------|
| `core/server.py` | FastAPI backend — SNMP + USB scan + reset |
| `core/libusb-1.0.dll` | ARM64 libusb DLL (dev only, gitignored) |
| `interface/electron/main.ts` | Electron main — window + backend lifecycle |
| `interface/build-electron.ts` | esbuild config (CJS output) |
| `interface/vite.config.ts` | Vite config (base: './', crossorigin strip, no modulePreload) |
| `interface/src/App.tsx` | Main React UI (printer list, detail, reset) |
| `interface/src/supabaseClient.ts` | Conditional Supabase client |
| `interface/src/LandingPage.tsx` | Cloud-hosted landing page |
| `interface/package.json` | main: dist-electron/main.cjs, extraResources config |
| `build-arm64.ps1` | Build automation (partially outdated) |
| `.gitignore` | Excludes build artifacts, *.spec, *.log |
