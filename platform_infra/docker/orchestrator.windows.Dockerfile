# ─────────────────────────────────────────────────────────────
# Smart-Monitor Orchestrator (Cross-Platform)
#   • Windows → mcr.microsoft.com/windows/servercore:ltsc2022
#   • Built via: docker build --platform ...
# ─────────────────────────────────────────────────────────────


#FROM mcr.microsoft.com/windows/servercore:ltsc2022
ARG BASE_IMAGE=mcr.microsoft.com/windows/servercore:ltsc2022
FROM ${BASE_IMAGE} AS windows
SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]

# OCI Metadata Labels
LABEL org.opencontainers.image.title="Smart Monitor Orchestrator" \
      org.opencontainers.image.description="Self-healing observability platform for hybrid systems" \
      org.opencontainers.image.source="https://github.com/anselem-okeke/Smart-Monitor" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="Anselem Dev" \
      org.opencontainers.image.authors="Anselem Okeke <anselem.okekee@gmail.com>" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.documentation="https://github.com/anselem-dev/smart-monitor/docs"

# Common environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SMARTMON_ROLE=orchestrator

# 1) Install Chocolatey
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","Set-ExecutionPolicy Bypass -Scope Process -Force; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')); choco feature enable -n=usePackageRepositoryOptimizations"]

# 2) Ensure the Chocolatey community source exists/enabled (some CI images override sources)
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco source remove -n=chocolatey -y *> $null; choco source add -n=chocolatey -s https://community.chocolatey.org/api/v2/ -y --priority=1; choco source enable -n=chocolatey"]

# 3) Install Python (pinned) and verify
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco install -y python --version=3.11.9 --no-progress"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","if (!(Test-Path 'C:\\Python311\\python.exe')) { throw 'Python not found at C:\\Python311\\python.exe' } ; & 'C:\\Python311\\python.exe' --version"]

# 4) Install smartmontools (non-portable MSI) and verify
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco install -y smartmontools --no-progress"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","& 'C:\\Program Files\\smartmontools\\bin\\smartctl.exe' --version"]

# 5) Persist PATH
#ENV PATH="C:\\Python311;C:\\Python311\\Scripts;C:\\Program Files\\smartmontools\\bin;C:\\ProgramData\\chocolatey\\bin;%PATH%"
ENV PATH="C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Python311;C:\Python311\Scripts;C:\Program Files\smartmontools\bin;C:\ProgramData\chocolatey\bin"

# 6) App payload
WORKDIR C:/app
COPY scripts                                  C:/app/scripts
COPY db                                       C:/app/db
COPY logs                                     C:/app/logs
COPY utils                                    C:/app/utils
COPY config                                   C:/app/config
COPY requirements.txt                          C:/app/requirements.txt
COPY main.py                                   C:/app/main.py
COPY platform_infra/docker/healthcheck.py      C:/app/healthcheck.py
COPY platform_infra/docker/entrypoint.ps1      C:/app/entrypoint.ps1

# Switch to cmd just for pip
SHELL ["cmd","/S","/C"]

RUN "C:\Python311\python.exe" -m pip install --upgrade pip wheel setuptools
RUN "C:\Python311\python.exe" -m pip install -r C:\app\requirements.txt
RUN "C:\Python311\python.exe" -m pip install psutil

# Switch back to PowerShell for the rest
SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]

# 8) Healthcheck + entrypoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["powershell","-NoProfile","-Command","try { & 'C:\\Python311\\python.exe' 'C:\\app\\healthcheck.py' } catch { exit 1 }"]
#CMD ["powershell","-NoProfile","-File","C:\\app\\entrypoint.ps1"]
ENTRYPOINT ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File","C:\\app\\entrypoint.ps1"]









