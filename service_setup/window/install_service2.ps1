# install_service2.ps1
param(
    [string]$ServiceName = "SmartMonitor",
    [string]$PythonExe   = "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe",
    [string]$AppPath     = "Z:\DevOps\section8_vprofile_project_manual_automation\vprofile-project\vagrant\Manual_provisioning_WinMacIntel\Smart-Monitor\main.py",
    [string]$AppDir      = "Z:\DevOps\section8_vprofile_project_manual_automation\vprofile-project\vagrant\Manual_provisioning_WinMacIntel\Smart-Monitor",
    [string]$DataDir     = "C:\ProgramData\SmartMonitor",
    # IP or DNS name of the Linux Postgres VM
    [string]$DbHost      = "192.168.56.11",
    # optional: DB creds / name (must match what you created on the VM)
    [string]$DbName      = "smartdb",
    [string]$DbUser      = "smart",
    [string]$DbPass      = "smartpass",
    [int]$DbPort         = 5438
)

# Ensure NSSM is installed
if (-not (Get-Command nssm.exe -ErrorAction SilentlyContinue)) {
    Write-Error "NSSM not found. Install with: choco install nssm -y"
    exit 1
}

# Ensure data/log directories
$LogDir = Join-Path $DataDir "logs"
New-Item -Force -ItemType Directory $DataDir | Out-Null
New-Item -Force -ItemType Directory $LogDir  | Out-Null

# Install/Update service
if (-not (nssm status $ServiceName 2>$null)) {
    nssm install $ServiceName $PythonExe $AppPath
}
nssm set $ServiceName AppDirectory $AppDir

# Build DATABASE_URL for Postgres
$databaseUrl = "postgresql://$DbUser`:$DbPass@$DbHost`:$DbPort/$DbName"

# Environment variables for the service
# NOTE: Do NOT set SMARTMONITOR_DB_PATH (that forces SQLite).
$envblock = @"
DATABASE_URL=$databaseUrl
PYTHONUNBUFFERED=1
LOG_LEVEL=INFO
SMARTCTL=C:\Program Files\smartmontools\bin\smartctl.exe
DRY_RUN=true
SMARTMON_API_KEY=dev-secret
SMARTMON_APPROVED_JSON=C:\ProgramData\SmartMonitor\approved_services.json
SMARTMON_SECRET_KEY=dev-please-change
"@

nssm set $ServiceName AppEnvironmentExtra $envblock

# Log rotation
nssm set $ServiceName AppStdout "$LogDir\smartmonitor.out.log"
nssm set $ServiceName AppStderr "$LogDir\smartmonitor.err.log"
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateOnline 1
nssm set $ServiceName AppRotateBytes 10485760   # 10 MB

# Recovery
nssm set $ServiceName AppExit Default Restart

# Run as LocalSystem
nssm set $ServiceName ObjectName LocalSystem

# Start (or restart) the service
if (nssm status $ServiceName 2>$null) {
    nssm restart $ServiceName
} else {
    nssm start $ServiceName
}

Write-Host "[OK] Service $ServiceName installed/updated and running"
Write-Host "Logs: $LogDir\smartmonitor.out.log / smartmonitor.err.log"
Write-Host "DATABASE_URL: $databaseUrl"
