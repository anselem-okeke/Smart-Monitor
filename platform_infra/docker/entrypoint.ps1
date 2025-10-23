<#
───────────────────────────────────────────────
 Smart-Monitor Orchestrator — Windows Entrypoint
 - Waits for DB
 - Logs startup info
 - Launches orchestrator main process
───────────────────────────────────────────────
#>

$ErrorActionPreference = "Stop"

function Log($msg) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $msg"
}

Log "Starting Smart-Monitor Orchestrator (Windows mode)"
Log "User: $env:USERNAME | Host: $env:COMPUTERNAME"

if (-not $env:DATABASE_URL) {
    Write-Error "DATABASE_URL not set"
    exit 1
}
if (-not $env:SMARTMON_API_KEY) {
    Write-Error "SMARTMON_API_KEY not set"
    exit 1
}

# Wait for DB connectivity (simple retry loop)
Log "Waiting for database..."
$maxRetries = 10
for ($i = 0; $i -lt $maxRetries; $i++) {
    try {
        python - <<'PYCODE'
import os, psycopg
try:
    psycopg.connect(os.getenv("DATABASE_URL")).close()
except Exception as e:
    raise SystemExit(1)
PYCODE
        Log "Database reachable."
        break
    } catch {
        Log "DB not reachable, retrying in 5s..."
        Start-Sleep -Seconds 5
    }
    if ($i -eq $maxRetries - 1) {
        Log "Database not reachable after multiple attempts, exiting."
        exit 1
    }
}

# Launch orchestrator main loop
Log "Running main orchestrator loop..."
python C:\app\main.py

