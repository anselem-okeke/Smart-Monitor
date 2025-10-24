# Windows Server 2022 (matches GH windows-2022 runner)
FROM mcr.microsoft.com/windows/servercore:ltsc2022

SHELL ["powershell","-Command"]


# --- 1) Install Python 3.11 and verify in THIS layer ---
RUN Write-Host '[BUILD] Windows Orchestrator' ; \
    Write-Host '[SETUP] Downloading Python 3.11 ...' ; \
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; \
    Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe' -OutFile 'C:\\python-installer.exe' ; \
    Start-Process -FilePath 'C:\\python-installer.exe' -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0' -Wait ; \
    Remove-Item 'C:\\python-installer.exe' -Force ; \
    # Make python available to THIS layer's PowerShell session
    [Environment]::SetEnvironmentVariable('Path', 'C:\Program Files\Python311;C:\Program Files\Python311\Scripts;' + [Environment]::GetEnvironmentVariable('Path','Process'), 'Process') ; \
    & 'C:\Program Files\Python311\python.exe' --version

# --- 2) Tools via choco (optional) ---
RUN Set-ExecutionPolicy Bypass -Scope Process -Force ; \
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; \
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')) ; \
    choco install -y smartmontools ; \
    & `"C:\Program Files\smartmontools\bin\smartctl.exe`" --version

# --- 3) Persist PATH for subsequent layers & runtime ---
ENV PATH="C:\\Program Files\\Python311;C:\\Program Files\\Python311\\Scripts;C:\\ProgramData\\chocolatey\\bin;%PATH%"

WORKDIR /app

# Copy app
COPY scripts /app/scripts
COPY db /app/db
COPY logs /app/logs
COPY utils /app/utils
COPY config /app/config
COPY main.py /app/main.py
COPY requirements.txt /app/requirements.txt
COPY platform_infra/docker/healthcheck.py /app/healthcheck.py
COPY platform_infra/docker/entrypoint.ps1 /app/entrypoint.ps1

# Install deps
RUN python -m pip install --upgrade pip wheel setuptools ; \
    pip install -r C:\app\requirements.txt ; \
    pip install psutil

# Healthcheck + entrypoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["powershell","-Command","try { python C:\\app\\healthcheck.py } catch { exit 1 }"]

CMD ["powershell","-File","C:\\app\\entrypoint.ps1"]
