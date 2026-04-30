#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo Project root: "$PROJECT_ROOT"
cd "$PROJECT_ROOT/lightshowai"

ENV_FILE="$PROJECT_ROOT/.env.local"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

if ! command -v gunicorn >/dev/null 2>&1; then
  echo "gunicorn is not installed in the active environment."
  echo 'Run: pip install -e .'
  exit 1
fi

: "${TILED_URL:?TILED_URL is not set. Add it to .env.local}"
: "${TILED_API_KEY:?TILED_API_KEY is not set. Add it to .env.local}"
: "${XAS_SANDBOX_URL:?XAS_SANDBOX_URL is not set. Add it to .env.local}"

exec gunicorn \
  --workers 1 \
  --worker-class gthread \
  --threads 8 \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile - \
  --bind 127.0.0.1:8443 \
  xas_ui:server