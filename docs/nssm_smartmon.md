### Installation and Uninstallation Steps
The installation is done through nssm, ensure that nssm is installed on
your windows machine using `chocolatey`
---

#### Setting up Env
1) Inspect what’s set now, If `AppEnvironment` prints anything, it wins over `AppEnvironmentExtra`.
```shell
nssm get SmartMonitor AppEnvironment
nssm get SmartMonitor AppEnvironmentExtra
nssm get SmartMonitor AppDirectory
nssm get SmartMonitor Application
```
2) Clear any overriding block
```shell
# Clear the primary environment block (if it exists)
nssm set SmartMonitor AppEnvironment ""
```
3) Overwrite the entire Extra env in one go (with 5438)
- `Note`: NSSM expects the whole block in one call. If you only set one line, it replaces the block with just that one line.
```shell
$DbHost="192.168.56.11"
$DbPort=5438
$DbName="mydb"
$DbUser="myuser"
$DbPass="mypass"
$databaseUrl = "postgresql://$DbUser`:$DbPass@$DbHost`:$DbPort/$DbName"

$envblock = @"
DATABASE_URL=$databaseUrl
PYTHONUNBUFFERED=1
LOG_LEVEL=INFO
SMARTMON_API_KEY=dev-secret
SMARTMON_APPROVED_JSON=C:\ProgramData\SmartMonitor\approved_services.json
SMARTMON_SECRET_KEY=dev-please-change
SMARTCTL=C:\Program Files\smartmontools\bin\smartctl.exe
"@

nssm set SmartMonitor AppEnvironmentExtra $envblock
```
4) Restart and verify
```shell
nssm restart SmartMonitor
nssm get SmartMonitor AppEnvironment
nssm get SmartMonitor AppEnvironmentExtra
```
- You should now see:
```shell
DATABASE_URL=postgresql://myuser:mypass@192.168.56.11:5438/mydb
...
```

5) If it still shows 5432

- Make sure you’re running the same nssm.exe that installed the service (Admin PowerShell).

- Try the interactive editor (easy way to spot overrides):
```shell
nssm edit SmartMonitor
```
- In the GUI:

  - Check AppEnvironment (should be empty). 
  - Update AppEnvironmentExtra with the full block. 
  - Save → Restart.
- Alternatively, reapply via `sc.exe` works because NSSM stores env as REG_MULTI_SZ
```shell
$k = 'HKLM:\SYSTEM\CurrentControlSet\Services\SmartMonitor\Parameters'
New-Item -Path $k -Force | Out-Null
$multi = @(
  "DATABASE_URL=$databaseUrl",
  "PYTHONUNBUFFERED=1",
  "LOG_LEVEL=INFO",
  "SMARTMON_API_KEY=dev-secret",
  "SMARTMON_APPROVED_JSON=C:\ProgramData\SmartMonitor\approved_services.json",
  "SMARTMON_SECRET_KEY=dev-please-change",
  "SMARTCTL=C:\Program Files\smartmontools\bin\smartctl.exe"
)
New-ItemProperty -Path $k -Name Environment -PropertyType MultiString -Value $multi -Force | Out-Null
Restart-Service SmartMonitor
```
6) Prove the service is using 5438

   - Easiest: log the connection string once on startup or just the port in Python service.
   - Or check connectivity from the Windows host:
```shell
Test-NetConnection 192.168.56.11 -Port 5438
```
#### Uninstallation Steps
1) Stop it (if running)
```shell
nssm stop SmartMonitor
Stop-Service SmartMonitor
```

2) Remove the service
```shell
nssm remove SmartMonitor confirm
```
- The confirm flag skips the interactive prompt.

- If you don’t have nssm in PATH, run with the full path to nssm.exe.

  - If NSSM isn’t available

  - You can still delete the service via SCM:
```shell
sc stop SmartMonitor
sc delete SmartMonitor
```
3) Clean up optional artifacts
   - Logs (from your script):
```makefile
C:\ProgramData\SmartMonitor\logs\
C:\ProgramData\SmartMonitor\
Z:\DevOps\...\Smart-Monitor\
```

4) Verify removal
 - No output / “The specified service does not exist” = removed
```shell
Get-Service SmartMonitor -ErrorAction SilentlyContinue
# or
sc query SmartMonitor
```
5) If registry cleanup is needed (rare)
 - NSSM stores settings under:
 ```makefile
 HKLM\SYSTEM\CurrentControlSet\Services\SmartMonitor
```
 - It should be removed by `sc delete`. If it lingers:
```shell
Remove-Item "HKLM:\SYSTEM\CurrentControlSet\Services\SmartMonitor" -Recurse -Force
```
6) Reinstall later (quick reminder)
```shell
nssm install SmartMonitor "C:\Python\python.exe" "C:\path\to\main.py"
nssm set SmartMonitor AppDirectory "C:\path\to\appdir"
nssm set SmartMonitor AppEnvironmentExtra "<your ENV block>"
nssm start SmartMonitor
```