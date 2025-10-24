# Windows Server 2022 base
FROM mcr.microsoft.com/windows/servercore:ltsc2022
SHELL ["powershell","-Command"]

# 1) Install Chocolatey once
RUN Set-ExecutionPolicy Bypass -Scope Process -Force ; \
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; \
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# 2) Install Python + smartmontools, refresh PATH for THIS layer, verify both
RUN choco install -y python --version=3.11.9 smartmontools ; \
    [Environment]::SetEnvironmentVariable('Path', 'C:\Program Files\Python311;C:\Program Files\Python311\Scripts;C:\Program Files\smartmontools\bin;' + [Environment]::GetEnvironmentVariable('Path','Process'), 'Process') ; \
    python --version ; \
    smartctl --version

# 3) Persist PATH for subsequent layers & runtime
ENV PATH="C:\\Program Files\\Python311;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\smartmontools\\bin;C:\\ProgramData\\chocolatey\\bin;%PATH%"

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
