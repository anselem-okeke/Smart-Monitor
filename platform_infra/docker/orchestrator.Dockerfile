# ─────────────────────────────────────────────────────────────
# Smart-Monitor Orchestrator (Cross-Platform, Multi-Stage)
#   • Linux   → python:3.11-slim-bookworm
#   • Windows → mcr.microsoft.com/windows/servercore:ltsc2022
#   • Built via: docker buildx build --platform ...
# ─────────────────────────────────────────────────────────────

ARG OS=linux
ARG BASE_IMAGE=python:3.11-slim-bookworm

# ------------STAGE 1 - BUILDER ------------------
FROM ${BASE_IMAGE} AS builder
WORKDIR /src
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN python -m pip install --upgrade pip wheel setuptools && \
    python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------- STAGE 2 – RUNTIME BASE ----------
FROM ${BASE_IMAGE} AS base
WORKDIR /app

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

# Copy orchestrator code & built wheels
COPY scripts/ /app/scripts/
COPY db/ /app/db/
COPY logs/ /app/logs/
COPY utils/ /app/utils/
COPY config/ /app/config/
COPY main.py/ /app/
COPY requirements.txt /app/
COPY --from=builder /wheels /wheels

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-index --find-links=/wheels /wheels/*

# Common entry files (Linux + Windows)
COPY platform_infra/docker/entrypoint.sh /app/entrypoint.sh
COPY platform_infra/docker/entrypoint.ps1 /app/entrypoint.ps1
COPY platform_infra/docker/healthcheck.py /app/healthcheck.py
RUN chmod +x /app/entrypoint.sh || true

# ─────────────────────────────────────────────────────────────
# LINUX VARIANT
# ─────────────────────────────────────────────────────────────
FROM base AS linux
ARG OS=linux
RUN echo "[BUILD] Linux Orchestrator" && \
    apt-get update && apt-get install -y systemctl dbus util-linux smartmontools --no-install-recommends \
        ca-certificates curl tzdata procps && \
    rm -rf /var/lib/apt/lists/*
# Non-root user
RUN useradd -u 10001 -m -s /usr/sbin/nologin appuser
USER appuser
RUN usermod -aG disk appuser

# Healthcheck (invokes /app/orchestrator/healthcheck.py)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 /app/orchestrator/healthcheck.py || exit 1

CMD ["bash", "/app/entrypoint.sh"]

# ─────────────────────────────────────────────────────────────
# WINDOWS VARIANT
# ─────────────────────────────────────────────────────────────
FROM mcr.microsoft.com/windows/servercore:ltsc2022 AS windows
ARG OS=windows
SHELL ["powershell", "-Command"]

# --- 1. Install Python 3.11 (quietly) ---
RUN Write-Host '[BUILD] Windows Orchestrator' ; \
    Write-Host '[SETUP] Downloading Python 3.11 ...' ; \
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; \
    Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe' -OutFile 'C:\\python-installer.exe' ; \
    Start-Process -FilePath 'C:\\python-installer.exe' -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0' -Wait ; \
    Remove-Item 'C:\\python-installer.exe' -Force ; \
    Write-Host '[OK] Python installed.' ; \
    python --version

# --- 2. Install Chocolatey and smartmontools ---
RUN Set-ExecutionPolicy Bypass -Scope Process -Force ; \
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 ; \
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1')) ; \
    choco install -y smartmontools ; \
    Write-Host '[OK] smartmontools installed.' ; \
    smartctl --version

# --- 3. Environment paths ---
ENV PATH="C:\\Python311;C:\\Python311\\Scripts;C:\\ProgramData\\chocolatey\\bin;${PATH}"
WORKDIR /app

# --- 4. Copy app files ---
COPY scripts /app/scripts
COPY db /app/db
COPY logs /app/logs
COPY utils /app/utils
COPY config /app/config
COPY main.py /app/main.py
COPY requirements.txt /app/requirements.txt
COPY platform_infra/docker/healthcheck.py /app/healthcheck.py
COPY platform_infra/docker/entrypoint.ps1 /app/entrypoint.ps1

# --- 5. Install Python dependencies ---
RUN python -m pip install --upgrade pip wheel setuptools ; \
    pip install -r C:\\app\\requirements.txt ; \
    pip install psutil ; \
    Write-Host '[OK] Dependencies installed.'

# --- 6. Verify environment ---
RUN Write-Host '[VERIFY] smartctl + Python ...' ; \
    Get-Command smartctl ; \
    python --version

# --- 7. Healthcheck and entrypoint ---
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["powershell", "-Command", "try { python C:\\app\\healthcheck.py } catch { exit 1 }"]

CMD ["powershell", "-File", "C:\\app\\entrypoint.ps1"]


