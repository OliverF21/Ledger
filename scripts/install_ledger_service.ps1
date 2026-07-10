<#
.SYNOPSIS
  Install Ledger as an always-on Windows service named "Ledger" using NSSM.

.DESCRIPTION
  Builds the frontend to static files, then registers a single service that runs
  the FastAPI backend (which also serves the built SPA) on port 8000. The service
  starts at boot, runs without a logged-in user, and auto-restarts on crash.

  Why NSSM and not Docker: the MCP server reads ledger.db directly
  off this host's filesystem and Claude Desktop spawns it here; a true Windows
  service (no login required) is the right fit, and Docker Desktop on Windows
  needs a logged-in session.

.PARAMETER Python
  Full path to the Python interpreter that has the backend deps installed
  (prefer the venv, e.g. backend\.venv\Scripts\python.exe).

.EXAMPLE
  .\scripts\install_ledger_service.ps1 -Python "D:\OpenTrack\opentrack\backend\.venv\Scripts\python.exe"
#>
param(
  [Parameter(Mandatory = $true)][string]$Python,
  [int]$Port = 8000,
  [string]$ServiceName = "Ledger"
)

$ErrorActionPreference = "Stop"
$RepoRoot   = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$LogDir     = Join-Path $RepoRoot "logs"

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
  throw "nssm not found on PATH. Install it (e.g. 'choco install nssm') or download nssm.exe."
}
if (-not (Test-Path $Python)) { throw "Python interpreter not found: $Python" }

# 1. Build the frontend so FastAPI serves it single-port (no Vite dev server).
Write-Host "Building frontend (npm run build)..." -ForegroundColor Cyan
Push-Location $FrontendDir
try {
  if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) { npm install }
  npm run build
} finally { Pop-Location }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# 2. (Re)install the service. One worker: the app starts APScheduler in lifespan,
#    so multiple workers would double-fire syncs / weekly email / expiry sweeps.
if (nssm status $ServiceName 2>$null) {
  Write-Host "Service '$ServiceName' exists; reinstalling..." -ForegroundColor Yellow
  nssm stop $ServiceName 2>$null | Out-Null
  nssm remove $ServiceName confirm | Out-Null
}

$args = "-m uvicorn main:app --host 0.0.0.0 --port $Port"
nssm install $ServiceName $Python $args
nssm set $ServiceName AppDirectory $BackendDir
nssm set $ServiceName AppStdout (Join-Path $LogDir "ledger.out.log")
nssm set $ServiceName AppStderr (Join-Path $LogDir "ledger.err.log")
nssm set $ServiceName Start SERVICE_AUTO_START
nssm set $ServiceName AppExit Default Restart
nssm set $ServiceName AppEnvironmentExtra "PYTHONUNBUFFERED=1"

nssm start $ServiceName
Write-Host "`nService '$ServiceName' installed and started on port $Port." -ForegroundColor Green

# 3. Reminders the script can't safely do for you.
Write-Host @"

Next steps (one-time):
  * Keep the machine awake:
      powercfg /change standby-timeout-ac 0
      powercfg /change hibernate-timeout-ac 0
  * BIOS: set 'Restore on AC Power Loss' = Power On; disable Fast Startup.
  * Access from anywhere: install Tailscale here + on your other devices,
    then browse http://<this-host-magicdns>:$Port (e.g. http://ledger:$Port).
  * Set PROPOSAL_SERVICE_KEY in backend\.env (already generated if you ran the
    build) so Claude's propose_budget tool works.
  * Manage the service: nssm restart $ServiceName | nssm stop $ServiceName | nssm edit $ServiceName
"@ -ForegroundColor DarkGray
