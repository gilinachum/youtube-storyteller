#!/bin/bash
# deploy-dev.sh — Deploy StoryTeller to dev environment (us-west-2, Cognito auth)
#
# This script:
# 1. Restores public (non-overlay) versions of tracked files
# 2. Builds frontend with dev config
# 3. Deploys CDK stacks with stage=dev
# 4. Deploys agent to AgentCore Runtime (no Federate JWT)
# 5. Re-applies the private overlay afterward
#
# Required: .env with AGENT_RUNTIME_ID, etc.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

STAGE="dev"
REGION="us-west-2"
PREFIX="storyteller-dev"

echo "🔧 [$STAGE] Deploying StoryTeller to $REGION..."

# ── Step 1: Remove overlay (restore public versions) ────────────────────
OVERLAY_FILES=(
  frontend/src/auth.ts
  frontend/src/App.tsx
  frontend/src/api.ts
  infra/stacks/api_stack.py
  infra/stacks/frontend_stack.py
  scripts/deploy.sh
)

echo "📦 Restoring public (non-overlay) file versions..."
git update-index --no-skip-worktree "${OVERLAY_FILES[@]}" 2>/dev/null || true

# Stash overlay changes so we can restore later
git stash push -m "overlay-for-deploy-dev" -- "${OVERLAY_FILES[@]}" 2>/dev/null || true

# Ensure we have the committed (public) versions
git checkout -- "${OVERLAY_FILES[@]}"

# ── Step 2: Load env ────────────────────────────────────────────────────
if [ -f "$PROJECT_DIR/.env.dev" ]; then
  echo "📄 Loading .env.dev"
  set -a; source "$PROJECT_DIR/.env.dev"; set +a
elif [ -f "$PROJECT_DIR/.env" ]; then
  echo "📄 Loading .env (no .env.dev found)"
  set -a; source "$PROJECT_DIR/.env"; set +a
fi

# ── Step 3: Build frontend ──────────────────────────────────────────────
echo "🏗️  Building frontend for $STAGE..."
cd "$PROJECT_DIR/frontend"
VITE_AUTH_MODE=cognito \
VITE_API_URL=/api \
  npm run build
cd "$PROJECT_DIR"

# ── Step 4: CDK deploy ──────────────────────────────────────────────────
echo "☁️  Deploying CDK stacks (stage=$STAGE, region=$REGION)..."
cd "$PROJECT_DIR/infra"
CDK_DEFAULT_REGION="$REGION" cdk deploy --all \
  --context stage="$STAGE" \
  --require-approval never \
  --outputs-file "$PROJECT_DIR/cdk-outputs-$STAGE.json"
cd "$PROJECT_DIR"

echo "📋 CDK outputs saved to cdk-outputs-$STAGE.json"

# ── Step 5: Deploy agent to AgentCore Runtime ───────────────────────────
if [ -n "${AGENT_RUNTIME_ID_DEV:-}" ]; then
  echo "🚀 Deploying agent to AgentCore Runtime ($STAGE)..."
  DEPLOY_TS=$(date -u +%Y%m%d%H%M%S)
  MESSAGES_TABLE="${MESSAGES_TABLE:-$PREFIX-messages}"
  SESSIONS_TABLE="${SESSIONS_TABLE:-$PREFIX-sessions}"
  UPLOAD_BUCKET="${UPLOAD_BUCKET:-}"
  BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-6}"

  uv run agentcore deploy \
    --env MESSAGES_TABLE="$MESSAGES_TABLE" \
    --env SESSIONS_TABLE="$SESSIONS_TABLE" \
    --env UPLOAD_BUCKET="$UPLOAD_BUCKET" \
    --env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
    --env BEDROCK_REGION="$REGION" \
    --env DEPLOY_TS="$DEPLOY_TS" \
    -auc
else
  echo "⏭️  Skipping agent deploy (AGENT_RUNTIME_ID_DEV not set)"
fi

# ── Step 6: Re-apply overlay ────────────────────────────────────────────
echo "🔒 Re-applying private overlay..."
git stash pop 2>/dev/null || true
git update-index --skip-worktree "${OVERLAY_FILES[@]}" 2>/dev/null || true

echo ""
echo "✅ Dev deploy complete ($REGION)"
echo "   CDK outputs: cdk-outputs-$STAGE.json"
