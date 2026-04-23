#!/bin/bash
# bundle_chat.sh — Build the chat Lambda deployment package
# Uses uv venv (already set up) to copy installed packages

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist/chat"
VENV_SITE="$PROJECT_ROOT/.venv/lib/python3.13/site-packages"

echo "📦 Bundling chat Lambda..."
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# Ensure all deps are installed in uv venv
echo "  → Syncing uv venv..."
cd "$PROJECT_ROOT"
uv sync --quiet

# Copy installed packages from venv
echo "  → Copying packages from venv..."
cp -r "$VENV_SITE"/. "$DIST_DIR/"

# Remove unnecessary test dirs and .dist-info to reduce size
find "$DIST_DIR" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find "$DIST_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$DIST_DIR" -name "*.pyc" -delete 2>/dev/null || true

# Copy source code
echo "  → Copying source..."
cp -r "$PROJECT_ROOT/api/"* "$DIST_DIR/"
cp -r "$PROJECT_ROOT/agent" "$DIST_DIR/agent"

echo "✅ Chat Lambda bundled at: $DIST_DIR"
du -sh "$DIST_DIR"
