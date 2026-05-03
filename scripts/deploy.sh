#!/bin/bash
# deploy.sh — Unified deploy script for StoryTeller
#
# Usage:
#   ./scripts/deploy.sh dev    # Deploy to dev (us-west-2, Cognito)
#   ./scripts/deploy.sh prod   # Deploy to prod (us-east-1, Federate)
#
# No default — you must specify the environment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ]; then
  echo "❌ Usage: $0 <dev|prod>"
  echo ""
  echo "  dev   — Deploy to us-west-2 with Cognito auth"
  echo "  prod  — Deploy to us-east-1 with Federate auth"
  exit 1
fi

STAGE="$1"

case "$STAGE" in
  dev)
    exec bash "$SCRIPT_DIR/deploy-dev.sh"
    ;;
  prod)
    exec bash "$SCRIPT_DIR/deploy-prod.sh"
    ;;
  *)
    echo "❌ Unknown stage: $STAGE"
    echo "   Use 'dev' or 'prod'"
    exit 1
    ;;
esac
