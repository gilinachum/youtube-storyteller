#!/bin/bash
# test-e2e.sh — Run end-to-end browser tests (requires deployed app + Playwright)
# Usage: ./scripts/test-e2e.sh
# Required env vars:
#   APP_URL         — frontend URL
#   TEST_EMAIL      — test user email
#   TEST_PASSWORD   — test user password
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load env — prefer dev for local testing
if [ -f "$PROJECT_DIR/.env.dev" ]; then
  set -a
  source "$PROJECT_DIR/.env.dev"
  set +a
fi

export APP_URL="${APP_URL:?Set APP_URL env var}"

echo "🌐 Running E2E tests against $APP_URL..."
uv run pytest tests/test_e2e.py -v -m integration "$@"
