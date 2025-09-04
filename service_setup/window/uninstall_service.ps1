<#
.SYNOPSIS
  Uninstall the Smart-Monitor Windows service (NSSM) and optionally clean data/logs/env.

.PARAMETER ServiceName
  Name of the NSSM service (default: SmartMonitor)

.PARAMETER RemoveData
  Also delete C:\ProgramData\SmartMonitor\smart_factory_monitor.db and the data folder.

.PARAMETER RemoveLogs
  Also delete C:\ProgramData\SmartMonitor\logs\*.

.PARAMETER RemoveSystemEnv
  Remove system-wide env vars set for dev (SMARTMONITOR_DB_PATH, LOG_LEVEL, PYTHONUNBUFFERED).

.EXAMPLE
  .\uninstall_service.ps1
.EXAMPLE
  .\uninstall_service.ps1 -ServiceName MySmartMon -RemoveData -RemoveLogs -RemoveSystemEnv
#>

[CmdletBinding(SupportsShouldProcess)]
param(
  [string] $ServiceName     = "SmartMonitor",
  [switch] $RemoveData,
  [switch] $RemoveLogs,
  [switch] $RemoveSystemEnv
)

function Stop-Service-IfRunning {
  param([string]$Name)
  $s = sc.exe query $Name 2>$null
  if ($LASTEXITCODE -eq 0 -and $s -match "STATE\s+:\s+\d+\s+RUNNING") {
    Write-Host "[INFO] Stopping service $Name ..."
    nssm stop $Name 2>$null | Out-Null
    Start-Sleep -Seconds 2
  } else {
    Write-Host "[INFO] Service $Name not running."
  }
}

# 1) Ensure NSSM exists; fall back to SC if needed
$hasNssm = [bool](Get-Command nssm.exe -ErrorAction SilentlyContinue)
if (-not $hasNssm) {
  Write-Warning "NSSM not found in PATH. Falling back to 'sc.exe delete' (works if service exists)."
}

# 2) Stop service if running
Stop-Service-IfRunning -Name $ServiceName

# 3) Remove the service
if ($hasNssm) {
  Write-Host "[INFO] Removing service $ServiceName via NSSM ..."
  nssm remove $ServiceName confirm 2>$null | Out-Null
} else {
  Write-Host "[INFO] Removing service $ServiceName via SC ..."
  sc.exe delete $ServiceName | Out-Null
}

# 4) Optional cleanup
$DataRoot = "C:\ProgramData\SmartMonitor"
$DbPath   = Join-Path $DataRoot "smart_factory_monitor.db"
$LogDir   = Join-Path $DataRoot "logs"

if ($RemoveLogs) {
  if (Test-Path $LogDir) {
    Write-Host "[INFO] Deleting logs: $LogDir"
    Remove-Item -Recurse -Force $LogDir
  } else {
    Write-Host "[INFO] No logs to delete at $LogDir"
  }
}

if ($RemoveData) {
  if (Test-Path $DbPath) {
    Write-Host "[INFO] Deleting DB: $DbPath"
    Remove-Item -Force $DbPath
  }
  if (Test-Path $DataRoot) {
    Write-Host "[INFO] Removing data folder (if empty): $DataRoot"
    Remove-Item -Force $DataRoot -ErrorAction SilentlyContinue
  }
}

if ($RemoveSystemEnv) {
  Write-Host "[INFO] Removing system environment variables ..."
  [Environment]::SetEnvironmentVariable("SMARTMONITOR_DB_PATH", $null, "Machine")
  [Environment]::SetEnvironmentVariable("LOG_LEVEL", $null, "Machine")
  [Environment]::SetEnvironmentVariable("PYTHONUNBUFFERED", $null, "Machine")
  Write-Host "[INFO] You may need to restart PowerShell/Explorer for changes to reflect."
}

Write-Host "[DONE] Uninstall complete."
