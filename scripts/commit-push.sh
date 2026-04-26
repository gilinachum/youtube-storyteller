#!/usr/bin/env bash
# scripts/commit-push.sh — Commit and push with security scan
# Usage: ./scripts/commit-push.sh "commit message"
#
# Steps:
#   1. Run git-secrets scan on staged files
#   2. Run all tests (except E2E live)
#   3. Commit with provided message
#   4. Push to origin main using GitHub PAT from Secrets Manager
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# ── Args ────────────────────────────────────────────────────────────────
MSG="${1:?Usage: $0 \"commit message\"}"

# ── 1. Security scan ───────────────────────────────────────────────────
echo "🔒 Scanning for secrets..."
if ! command -v git-secrets &>/dev/null; then
    echo "❌ git-secrets not installed. Run: git secrets --install && git secrets --register-aws"
    exit 1
fi
git secrets --scan
echo "✅ No secrets found"

# ── 2. Run tests ──────────────────────────────────────────────────────
echo "🧪 Running tests..."
uv run pytest tests/ --ignore=tests/test_e2e.py --ignore=tests/test_e2e_live.py -q
echo "✅ Tests passed"

# ── 3. Stage & commit ────────────────────────────────────────────────
git add -A

if git diff --cached --quiet; then
    echo "⚠️  Nothing to commit"
    exit 0
fi

git commit -m "$MSG"
echo "✅ Committed"

# ── 4. Push ──────────────────────────────────────────────────────────
echo "🚀 Pushing to origin..."
PAT=$(aws secretsmanager get-secret-value --secret-id github/storyteller-pat --query SecretString --output text)
git push "https://gilinachum:${PAT}@github.com/gilinachum/youtube-storyteller.git" main
echo "✅ Pushed to main"
