#!/bin/bash
# deploy-all.sh — Deploy agent + frontend in one go
# Usage: ./scripts/deploy-all.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Agent Deploy ==="
bash "$SCRIPT_DIR/deploy.sh"

echo ""
echo "=== Frontend Deploy ==="
bash "$SCRIPT_DIR/deploy-frontend.sh"

echo ""
echo "🎉 Full deploy complete!"
