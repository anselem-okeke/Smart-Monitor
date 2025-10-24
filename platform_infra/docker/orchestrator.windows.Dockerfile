# Windows Server 2022 base
FROM mcr.microsoft.com/windows/servercore:ltsc2022
SHELL ["powershell","-Command"]

# 1) Install Chocolatey and ensure default source is configured
RUN Set-ExecutionPolicy Bypass -Scope Process -Force ; \
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; \
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')) ; \
    choco feature enable -n=usePackageRepositoryOptimizations ; \
    choco source add -n=chocolatey -s 'https://community.chocolatey.org/api/v2/' -y --priority=1

# 2) Install Python (latest stable) + smartmontools (with portable fallback), refresh PATH for THIS layer, verify
RUN $ErrorActionPreference='Stop' ; \
    choco install -y python --no-progress ; \
    try { choco install -y smartmontools --no-progress } catch { choco install -y smartmontools.portable --no-progress } ; \
    # Refresh PATH for the current process so commands work immediately
    $py='C:\Program Files\Python311' ; \
    $sm='C:\Program Files\smartmontools\bin' ; \
    if (Test-Path $sm) { $smUse=$sm } else { $smUse='C:\tools\smartmontools\bin' } ; \
    [Environment]::SetEnvironmentVariable('Path', "$py;$py\Scripts;$smUse;C:\ProgramData\chocolatey\bin;" + [Environment]::GetEnvironmentVariable('Path','Process'), 'Process') ; \
    python --version ; \
    smartctl --version

# 3) Persist PATH for subsequent layers & runtime
ENV PATH="C:\\Program Files\\Python311;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\smartmontools\\bin;C:\\tools\\smartmontools\\bin;C:\\ProgramData\\chocolatey\\bin;%PATH%"

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
