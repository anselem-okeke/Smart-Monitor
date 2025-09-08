#!/usr/bin/env bash

set -Eeuo pipefail

# Optional: load a local .env if present (so DOCKER_HUB_NAME/DOCKER_HUB_TOKEN work)
# absolute path to this script's directory (works even if called via symlink)
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ENV_FILE="${ENV_FILE:-$(realpath "$SCRIPT_DIR/../../.env")}"

echo "$SCRIPT_DIR"
echo "$ENV_FILE"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(sed -e 's/\r$//' "$ENV_FILE")
  set +a
else
  echo "Missing .env at: $ENV_FILE" >&2
  exit 1
fi

# Require these to be set (either exported or in .env)
: "${DOCKER_HUB_NAME:?Set DOCKER_HUB_NAME (Docker Hub username)}"
: "${DOCKER_HUB_TOKEN:?Set DOCKER_HUB_TOKEN (Docker Hub access token)}"

# Ensure a buildx builder exists
docker buildx inspect >/dev/null 2>&1 || docker buildx create --use

# Non-interactive login (works in scripts/CI)
echo "$DOCKER_HUB_TOKEN" | docker login -u "$DOCKER_HUB_NAME" --password-stdin

# Build & push multi-arch
docker buildx build --platform linux/amd64,linux/arm64 \
  -t "$DOCKER_HUB_NAME/smartmon-sqliteweb:latest" \
  --push .


