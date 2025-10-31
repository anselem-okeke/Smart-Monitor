<#
  Smart-Monitor GUI (Windows) — ENTRYPOINT
  - Normalizes PATH
  - Prints startup info
  - Launches Flask app via waitress-serve
#>

$ErrorActionPreference = "Stop"

# Normalize PATH so basic tools are available (sc, powershell, python)
$env:PATH = @(
  'C:\Windows\System32',
  'C:\Windows',
  'C:\Windows\System32\WindowsPowerShell\v1.0',
  'C:\Python311',
  'C:\Python311\Scripts',
  $env:PATH
) -join ';'

function Log($msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Write-Host "[$ts] $msg"
}

$port = $env:PORT; if (-not $port) { $port = 5003 }
$app  = $env:GUNICORN_APP; if (-not $app) { $app = 'gui.app:create_app' }

Log "Starting Smart-Monitor GUI (Windows)"
Log "User: $env:USERNAME | Host: $env:COMPUTERNAME"
Log "App: $app | Port: $port"

# Ensure basic directories (if your app writes to instance/logs)
New-Item -ItemType Directory -Path "C:\app\logs" -Force | Out-Null
New-Item -ItemType Directory -Path "C:\app\instance" -Force | Out-Null

# Launch Waitress (Gunicorn is Unix-only)
# waitress-serve expects module:function or module:callable()
# For Flask factory, use gui.app:create_app
$cmd = @(
  'C:\Python311\Scripts\waitress-serve.exe',
  "--listen=0.0.0.0:$port",
  $app
)

Log "Exec: $($cmd -join ' ')"
Start-Process -FilePath $cmd[0] -ArgumentList $cmd[1..($cmd.Length-1)] -NoNewWindow -Wait

