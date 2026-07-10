# Full Windows build pipeline for the Ledger desktop app (run on Windows).
#
#   1. build the frontend (frontend/dist)
#   2. bundle the backend with PyInstaller (backend/dist/ledger-backend/ledger-backend.exe)
#   3. build the Tauri installer (.exe / .msi) via NSIS
#
# Prereqs: Node + npm, Rust (rustup, MSVC toolchain), Python 3.11+, and the
# Microsoft C++ Build Tools + WebView2 runtime (bundled by Tauri's NSIS installer).
# Unsigned output — see README "First launch (Windows)".
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."

Write-Host "==> [1/3] frontend build"
Push-Location "$root\frontend"
if (-not (Test-Path node_modules)) { npm ci }
npm run build
Pop-Location

Write-Host "==> [2/3] backend bundle (PyInstaller)"
Push-Location "$root\backend"
if (-not (Test-Path venv\Scripts\python.exe)) {
  python -m venv venv
  .\venv\Scripts\pip install -q -r requirements.txt
}
.\venv\Scripts\pip install -q pyinstaller
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }
.\venv\Scripts\pyinstaller ledger.spec --noconfirm
Pop-Location

Write-Host "==> [3/3] Tauri installer (NSIS)"
Push-Location "$root\desktop"
if (-not (Test-Path node_modules)) { npm install }
if ($env:TAURI_SIGNING_PRIVATE_KEY) {
  Write-Host "    (release: signing updater artifacts via tauri.release.conf.json)"
  npx tauri build --bundles nsis --config src-tauri/tauri.release.conf.json
} else {
  npx tauri build --bundles nsis
}
Pop-Location

Write-Host "==> done — installer under desktop\src-tauri\target\release\bundle\nsis\"
