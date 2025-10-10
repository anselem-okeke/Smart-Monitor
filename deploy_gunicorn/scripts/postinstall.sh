#!/usr/bin/env bash
set -euo pipefail

### ====== CONFIG (override with env vars before running) ======
APP_NAME="${APP_NAME:-Smart-Monitor}"
APP_USER="${APP_USER:-smartmon}"
APP_GROUP="${APP_GROUP:-smartmon}"
APP_ROOT="${APP_ROOT:-/opt/Smart-Monitor}"
GUI_DIR="${GUI_DIR:-$APP_ROOT/gui}"
DB_DIR="${DB_DIR:-/var/lib/smart-monitor}"
DB_PATH="${DB_PATH:-$DB_DIR/smart_factory_monitor.db}"
ETC_DIR="${ETC_DIR:-/etc/smart-monitor}"
ENV_FILE="${ENV_FILE:-$ETC_DIR/env}"

# If your repo root isn’t the CWD when running, set REPO_SRC explicitly.
REPO_SRC="${REPO_SRC:-$(pwd)}"

# If your requirements live at repo root; change if needed
REQ_FILE="${REQ_FILE:-$REPO_SRC/requirements.txt}"

# Package set
APT_PKGS="${APT_PKGS:-nginx python3-venv sqlite3 rsync}"

### ====== PRE-FLIGHT ======
if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo $0)"; exit 1
fi

echo "==> Installing packages: $APT_PKGS"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y $APT_PKGS

echo "==> Creating system user/group: $APP_USER"
id -u "$APP_USER" &>/dev/null || adduser --system --group "$APP_USER"

echo "==> Creating directories"
mkdir -p "$APP_ROOT" "$DB_DIR" "$ETC_DIR"
chown -R "$APP_USER:$APP_GROUP" "$APP_ROOT" "$DB_DIR"
chmod 0755 "$APP_ROOT" "$DB_DIR"

echo "==> Syncing repo to $APP_ROOT (this replaces files that changed)"
# Exclude venvs and pyc
rsync -a --delete \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '*.pyc' \
  "$REPO_SRC/" "$APP_ROOT/"

### ====== PYTHON / VENV ======
echo "==> Ensuring venv and Python dependencies"
cd "$GUI_DIR"
python3 -m venv .venv --copies
source .venv/bin/activate
python -m pip install -U pip wheel setuptools

# Repair known bad pin (if present) and BOM at top of requirements
if [[ -f "$REQ_FILE" ]]; then
  # strip UTF-8 BOM if any (safe no-op otherwise)
  sed -i '1s/^\xEF\xBB\xBF//' "$REQ_FILE"
  # fix bad blinker pin if someone committed 1.9.0 (doesn't exist)
  if grep -qE '^blinker==1\.9\.0$' "$REQ_FILE"; then
    sed -i 's/^blinker==1\.9\.0$/blinker==1.8.2/' "$REQ_FILE"
  fi
  pip install -r "$REQ_FILE"
else
  echo "WARN: requirements file not found at $REQ_FILE; installing minimal runtime"
fi

# Make sure critical runtime deps are present
pip install --upgrade gunicorn Flask-Limiter python-dotenv

### ====== GUNICORN CONFIG ======
GCONF="$GUI_DIR/gunicorn.conf.py"
if [[ ! -f "$GCONF" ]]; then
  echo "==> Writing default $GCONF"
  cat > "$GCONF" <<'PY'
bind = "127.0.0.1:5003"
workers = 2
threads = 4
timeout = 60
graceful_timeout = 30
keepalive = 30
worker_class = "gthread"
accesslog = "-"
errorlog = "-"
loglevel = "info"
PY
  chown "$APP_USER:$APP_GROUP" "$GCONF"
fi

### ====== ENV FILE ======
if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Creating $ENV_FILE"
  install -m 0640 -o root -g root /dev/stdin "$ENV_FILE" <<ENV
# Smart-Monitor environment
DB_PATH=$DB_PATH
FLASK_ENV=production
# Add other knobs here e.g.
# RATE_LIMIT_DEFAULT=30 per minute
ENV
else
  echo "==> $ENV_FILE exists; leaving as-is"
fi

### ====== SQLITE SETUP ======
echo "==> Ensuring DB dir permissions and enabling WAL (non-fatal if DB not created yet)"
chown -R "$APP_USER:$APP_GROUP" "$DB_DIR"
# Create empty DB if missing (app may also create it)
if [[ ! -f "$DB_PATH" ]]; then
  sudo -u "$APP_USER" sqlite3 "$DB_PATH" "VACUUM;"
fi
# Enable WAL (ignore errors if sqlite version doesn’t support)
sudo -u "$APP_USER" sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL;" || true

echo "==> postinstall complete."
