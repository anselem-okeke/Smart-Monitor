ARG BASE_IMAGE=mcr.microsoft.com/windows/servercore:ltsc2022
FROM ${BASE_IMAGE} as windows

SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]

LABEL org.opencontainers.image.title="Smart Monitor GUI" \
      org.opencontainers.image.description="Flask UI via Waitress on Windows" \
      org.opencontainers.image.source="https://github.com/anselem-okeke/Smart-Monitor" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=C:\app \
    PORT=5003 \
    GUNICORN_APP=gui.app:create_app \
    PYTHONPATH=C:\app

# Chocolatey + Python
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","Set-ExecutionPolicy Bypass -Scope Process -Force; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1')); choco feature enable -n=usePackageRepositoryOptimizations"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco source remove -n=chocolatey -y *> $null; choco source add -n=chocolatey -s https://community.chocolatey.org/api/v2/ -y --priority=1; choco source enable -n=chocolatey"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","choco install -y python --version=3.11.9 --no-progress"]
RUN ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command","if (!(Test-Path 'C:\\Python311\\python.exe')) { throw 'Python not found at C:\\Python311\\python.exe' } ; & 'C:\\Python311\\python.exe' --version"]

# PATH
ENV PATH="C:\Windows\System32;C:\Windows;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Python311;C:\Python311\Scripts;C:\ProgramData\chocolatey\bin"

# App payload
WORKDIR C:/app
COPY gui/                                                   C:/app/gui/
COPY db/                                                    C:/app/db/
COPY scripts/                                               C:/app/scripts/
COPY utils/                                                 C:/app/utils/
COPY config/                                                C:/app/config/
COPY requirements.txt                                       C:/app/requirements.txt
COPY platform_infra/docker/entrypoint.gui.windows.ps1       C:/app/entrypoint.ps1
COPY platform_infra/docker/healthcheck.gui.py               C:/app/healthcheck.py

# remove: COPY logs C:/app/logs
RUN powershell -NoProfile -Command "New-Item -ItemType Directory -Path 'C:\app\logs','C:\app\instance' -Force | Out-Null"

# Use cmd for pip (simpler/faster)
SHELL ["cmd","/S","/C"]
RUN "C:\Python311\python.exe" -m pip install --upgrade pip wheel setuptools
RUN "C:\Python311\python.exe" -m pip install -r C:\app\requirements.txt
RUN "C:\Python311\python.exe" -m pip install waitress

# Back to PowerShell
SHELL ["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command"]

EXPOSE 5003
HEALTHCHECK --interval=30s --timeout=6s --retries=5 CMD ["powershell","-NoProfile","-ExecutionPolicy","Bypass","C:\\Python311\\python.exe","C:\\app\\healthcheck.py"]

ENTRYPOINT ["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File","C:\\app\\entrypoint.ps1"]
