# install_service.ps1
param(
    [string]$ServiceName = "SmartMonitor",
    [string]$PythonExe   = "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe",            # adjust if your python.exe is elsewhere
    [string]$AppPath     = "Y:\DevOps\section8_vprofile_project_manual_automation\vprofile-project\vagrant\Manual_provisioning_WinMacIntel\Smart-Monitor\main.py",   # adjust to where main.py lives
    [string]$AppDir      = "Y:\DevOps\section8_vprofile_project_manual_automation\vprofile-project\vagrant\Manual_provisioning_WinMacIntel\Smart-Monitor",
    [string]$DataDir     = "C:\ProgramData\SmartMonitor"
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

# Install service
nssm install $ServiceName $PythonExe $AppPath
nssm set $ServiceName AppDirectory $AppDir

# Environment variables for the service
$envblock = @"
SMARTMONITOR_DB_PATH=$DataDir\smart_factory_monitor.db
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1
"@
nssm set $ServiceName AppEnvironmentExtra $envblock

# Log rotation
nssm set $ServiceName AppStdout "$LogDir\smartmonitor.out.log"
nssm set $ServiceName AppStderr "$LogDir\smartmonitor.err.log"
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateOnline 1
nssm set $ServiceName AppRotateBytes 10485760   # 10 MB

# Recovery: auto-restart on exit/crash
nssm set $ServiceName AppExit Default Restart

# Run as LocalSystem (full service privileges)
nssm set $ServiceName ObjectName LocalSystem

# Start the service
nssm start $ServiceName

Write-Host "[OK] Service $ServiceName installed and started"
Write-Host "Logs: $LogDir\smartmonitor.out.log / smartmonitor.err.log"
