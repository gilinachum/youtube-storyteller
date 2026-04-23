#!/bin/bash
# test.sh — Run unit tests
# Usage: ./scripts/test.sh [pytest args]
# Examples:
#   ./scripts/test.sh                    # all unit tests
#   ./scripts/test.sh -v                 # verbose
#   ./scripts/test.sh -k "test_parse"    # filter by name
#   ./scripts/test.sh --tb=long          # full tracebacks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "🧪 Running unit tests..."
uv run pytest tests/ --ignore=tests/test_e2e.py "$@"
