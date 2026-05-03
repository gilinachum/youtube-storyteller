#!/bin/bash
# deploy-prod.sh — Deploy StoryTeller to prod environment (us-east-1, Federate/CFS auth)
#
# This script:
# 1. Ensures the private overlay is applied
# 2. Builds frontend with prod config
# 3. Deploys CDK stacks with stage=prod
# 4. Deploys agent to AgentCore Runtime (with Federate JWT)
# 5. Runs setup_midway.py for CFS protection
#
# Required: .env with AGENT_RUNTIME_ID, FEDERATE_AUDIENCE, etc.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

STAGE="prod"
REGION="us-east-1"
PREFIX="storyteller"

echo "🔧 [$STAGE] Deploying StoryTeller to $REGION..."

# ── Step 1: Ensure overlay is applied ───────────────────────────────────
OVERLAY_FILES=(
  frontend/src/auth.ts
  frontend/src/App.tsx
  frontend/src/api.ts
  infra/stacks/api_stack.py
  infra/stacks/frontend_stack.py
  scripts/deploy.sh
)

if [ -d "$PROJECT_DIR/private" ] && [ -f "$PROJECT_DIR/private/overlay.sh" ]; then
  echo "🔐 Applying private overlay..."
  bash "$PROJECT_DIR/private/overlay.sh"
  git update-index --skip-worktree "${OVERLAY_FILES[@]}" 2>/dev/null || true
else
  echo "⚠️  No private overlay found at private/overlay.sh"
  echo "   Deploying without Federate auth — are you sure?"
  read -p "   Continue? [y/N] " -n 1 -r
  echo
  [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi

# ── Step 2: Load env ────────────────────────────────────────────────────
if [ -f "$PROJECT_DIR/.env.prod" ]; then
  echo "📄 Loading .env.prod"
  set -a; source "$PROJECT_DIR/.env.prod"; set +a
elif [ -f "$PROJECT_DIR/.env" ]; then
  echo "📄 Loading .env"
  set -a; source "$PROJECT_DIR/.env"; set +a
fi

# ── Step 3: Build frontend ──────────────────────────────────────────────
echo "🏗️  Building frontend for $STAGE..."
cd "$PROJECT_DIR/frontend"
VITE_AUTH_MODE=federate \
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

# ── Step 5: Deploy agent to AgentCore Runtime (with Federate JWT) ───────
AGENT_RUNTIME_ID="${AGENT_RUNTIME_ID:?Set AGENT_RUNTIME_ID env var}"
MESSAGES_TABLE="${MESSAGES_TABLE:-$PREFIX-messages}"
SESSIONS_TABLE="${SESSIONS_TABLE:-$PREFIX-sessions}"
UPLOAD_BUCKET="${UPLOAD_BUCKET:?Set UPLOAD_BUCKET env var}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-6}"
FEDERATE_AUDIENCE="${FEDERATE_AUDIENCE:-storyteller-cognito}"

echo "🚀 Deploying agent to AgentCore Runtime ($STAGE)..."
DEPLOY_TS=$(date -u +%Y%m%d%H%M%S)
uv run agentcore deploy \
  --env MESSAGES_TABLE="$MESSAGES_TABLE" \
  --env SESSIONS_TABLE="$SESSIONS_TABLE" \
  --env UPLOAD_BUCKET="$UPLOAD_BUCKET" \
  --env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
  --env BEDROCK_REGION="$REGION" \
  --env DEPLOY_TS="$DEPLOY_TS" \
  -auc

# Restore Federate JWT authorizer on the runtime
echo "🔑 Restoring Federate JWT authorizer..."
FEDERATE_DISCOVERY_URL="https://idp.federate.amazon.com/.well-known/openid-configuration"
uv run agentcore config set-auth \
  --runtime-id "$AGENT_RUNTIME_ID" \
  --type jwt \
  --discovery-url "$FEDERATE_DISCOVERY_URL" \
  --audience "$FEDERATE_AUDIENCE" 2>/dev/null || echo "   (set-auth not available — configure JWT manually)"

# ── Step 6: CFS protection (Midway) ────────────────────────────────────
if [ -f "$PROJECT_DIR/infra-private/setup_midway.py" ]; then
  echo "🛡️  Applying CFS protection..."
  cd "$PROJECT_DIR"
  uv run python3 infra-private/setup_midway.py
else
  echo "⏭️  Skipping CFS setup (infra-private/setup_midway.py not found)"
fi

echo ""
echo "✅ Prod deploy complete ($REGION)"
echo "   CDK outputs: cdk-outputs-$STAGE.json"
