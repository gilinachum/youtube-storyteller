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
# Fetch PAT from Secrets Manager. Secret name + GitHub repo URL are
# overridable via env vars so forks can use their own:
#   GH_PAT_SECRET=<secrets-manager-secret-id>     (default: github/storyteller-pat)
#   GH_REPO_URL=<full https URL with placeholder> (default: this repo's)
#   GH_USER=<github username>                     (default: extract from remote)
SECRET_ID="${GH_PAT_SECRET:-github/storyteller-pat}"
REPO_URL="${GH_REPO_URL:-$(git remote get-url origin)}"
GH_USER="${GH_USER:-$(git remote get-url origin | sed -E 's|.*github.com[:/]([^/]+)/.*|\1|')}"

PAT=$(aws secretsmanager get-secret-value --secret-id "$SECRET_ID" --query SecretString --output text)
# If the secret is JSON, try to extract the token field; otherwise treat the whole value as the token
if echo "$PAT" | python3 -c 'import json,sys; json.loads(sys.stdin.read())' 2>/dev/null; then
    PAT=$(echo "$PAT" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('token', d.get('pat', '')))")
fi

# Remove any existing scheme/credentials from REPO_URL
REPO_PATH=$(echo "$REPO_URL" | sed -E 's|^https?://([^@]+@)?||; s|\.git$||')
git push "https://${GH_USER}:${PAT}@${REPO_PATH}.git" main
echo "✅ Pushed to main"
