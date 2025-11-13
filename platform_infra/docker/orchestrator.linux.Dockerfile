#  Author: Anselem Okeke
#    MIT License
#    Copyright (c) 2025 Anselem Okeke
#    See LICENSE file in the project root for full license text.
# ─────────────────────────────────────────────────────────────
# Smart-Monitor Orchestrator (Cross-Platform, Multi-Stage)
#   • Linux   → python:3.11-slim-bookworm
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
COPY main.py /app/main.py
COPY requirements.txt /app/
COPY --from=builder /wheels /wheels

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-index --find-links=/wheels /wheels/*

# Common entry files (Linux + Windows)
COPY platform_infra/docker/entrypoint.sh /app/entrypoint.sh
COPY platform_infra/docker/entrypoint.ps1 /app/entrypoint.ps1
COPY platform_infra/docker/healthcheck.py /app/healthcheck.py
RUN chmod +x /app/entrypoint.sh || true

COPY platform_infra/docker_compose/systemctl-shim /usr/local/bin/systemctl-shim
RUN chmod +x /usr/local/bin/systemctl-shim

FROM base AS linux
ARG OS=linux
RUN echo "[BUILD] Linux Orchestrator" && \
    apt-get update && apt-get install -y systemd dbus util-linux smartmontools --no-install-recommends \
        ca-certificates curl tzdata procps && \
    rm -rf /var/lib/apt/lists/*

# create user and add to disk group
RUN useradd -u 10001 -m -s /usr/sbin/nologin appuser && \
    usermod -aG disk appuser

# Switch to non-root for runtime
USER appuser

# Healthcheck (invokes /app/orchestrator/healthcheck.py)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 /app/healthcheck.py || exit 1

CMD ["bash", "/app/entrypoint.sh"]