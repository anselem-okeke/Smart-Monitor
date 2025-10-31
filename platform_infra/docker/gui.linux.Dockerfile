# syntax=docker/dockerfile:1.7

##############################################
# STAGE 1 — Build Python wheels for fast install
##############################################
ARG PY_BASE=python:3.11-slim-bookworm
FROM ${PY_BASE} AS builder

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1

# Build deps only while building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only what we need to resolve deps
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip wheel setuptools \
 && python -m pip wheel --wheel-dir=/wheels -r requirements.txt

##############################################
# STAGE 2 — Runtime (non-root + gunicorn)
##############################################
FROM ${PY_BASE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ARG APP_USER=app
ENV APP_HOME=/app

# Minimal runtime libs (add libpq for psycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN addgroup --system ${APP_USER} \
 && adduser  --system --ingroup ${APP_USER} --home ${APP_HOME} ${APP_USER}

WORKDIR ${APP_HOME}

# Install deps into a venv from prebuilt wheels
COPY --from=builder /wheels /wheels
COPY requirements.txt ./requirements.txt
RUN python -m venv /venv \
 && /venv/bin/pip install --no-index --find-links=/wheels -r requirements.txt

# ── App code ─────────────────────────────────────────
# Copy GUI package and config files
COPY gui/         ${APP_HOME}/gui/
COPY db/          ${APP_HOME}/db/
COPY scripts/     ${APP_HOME}/scripts/
COPY utils/       ${APP_HOME}/utils/
COPY config/      ${APP_HOME}/config/
COPY logs/        ${APP_HOME}/logs/
COPY main.py      ${APP_HOME}/main.py

# Optional helper scripts
COPY platform_infra/docker/entrypoint.gui.linux.sh   ${APP_HOME}/entrypoint.sh
COPY platform_infra/docker/healthcheck.gui.py        ${APP_HOME}/healthcheck.py

# Ensure writable dirs; tighten ownership
RUN chmod +x ${APP_HOME}/entrypoint.sh \
 && mkdir -p ${APP_HOME}/instance ${APP_HOME}/logs \
 && chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

USER ${APP_USER}

# ── Runtime env knobs (safe defaults; override at run) ──
ENV HOST=0.0.0.0 \
    PORT=5003 \
    GUNICORN_BIND="0.0.0.0:5003" \
    WEB_CONCURRENCY=2 \
    WORKERS=2 \
    THREADS=4 \
    GUNICORN_TIMEOUT=60 \
    GUNICORN_KEEPALIVE=30 \
    GUNICORN_LOGLEVEL=info \
    GUNICORN_APP="gui.app:create_app" \
    GUNICORN_CONFIG="/app/gui/gunicorn.conf.py"

COPY platform_infra/docker/healthcheck.py /app/healthcheck.py
HEALTHCHECK --interval=30s --timeout=6s --retries=5 \
  CMD /venv/bin/python /app/healthcheck.py

EXPOSE 5003
ENTRYPOINT ["/bin/bash", "-lc", "/app/entrypoint.sh"]

