#!/bin/bash
# deploy-dev.sh — Deploy StoryTeller to dev environment (us-west-2, Cognito auth)
#
# This script:
# 1. Restores public (non-overlay) versions of tracked files
# 2. Builds frontend with dev config
# 3. Deploys CDK stacks with stage=dev
# 4. Deploys agent to AgentCore Runtime
# 5. Re-applies AgentCore runtime config (JWT authorizer + header allowlist)
# 6. Invalidates CloudFront cache
# 7. Re-applies the private overlay afterward
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

STAGE="dev"
REGION="us-west-2"
PREFIX="storyteller-dev"
AGENT_NAME="storytellerDev"

echo "🔧 [$STAGE] Deploying StoryTeller to $REGION..."

# ── Load env ────────────────────────────────────────────────────────────
if [ -f "$PROJECT_DIR/.env.dev" ]; then
  set -a; source "$PROJECT_DIR/.env.dev"; set +a
elif [ -f "$PROJECT_DIR/.env" ]; then
  set -a; source "$PROJECT_DIR/.env"; set +a
fi

# Required vars
AGENT_RUNTIME_ID="${AGENT_RUNTIME_ID_DEV:?Set AGENT_RUNTIME_ID_DEV in .env}"
EXECUTION_ROLE="${EXECUTION_ROLE_DEV:?Set EXECUTION_ROLE_DEV in .env}"
COGNITO_DISCOVERY_URL="${COGNITO_DISCOVERY_URL_DEV:?Set COGNITO_DISCOVERY_URL_DEV in .env}"
COGNITO_AUDIENCE="${COGNITO_AUDIENCE_DEV:?Set COGNITO_AUDIENCE_DEV in .env}"
MESSAGES_TABLE="${MESSAGES_TABLE_DEV:-$PREFIX-messages}"
SESSIONS_TABLE="${SESSIONS_TABLE_DEV:-$PREFIX-sessions}"
UPLOAD_BUCKET="${UPLOAD_BUCKET_DEV:?Set UPLOAD_BUCKET_DEV in .env}"
CF_DISTRIBUTION_ID="${CF_DISTRIBUTION_ID_DEV:-}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-6}"
S3_BUCKET="bedrock-agentcore-codebuild-sources-726941381086-$REGION"

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
git stash push -m "overlay-for-deploy-dev" -- "${OVERLAY_FILES[@]}" 2>/dev/null || true
git checkout -- "${OVERLAY_FILES[@]}"

# Cleanup function to re-apply overlay on exit (success or failure)
cleanup() {
  echo "🔒 Re-applying private overlay..."
  cd "$PROJECT_DIR"
  git stash pop 2>/dev/null || true
  git update-index --skip-worktree "${OVERLAY_FILES[@]}" 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 2: Build frontend ──────────────────────────────────────────────
echo "🏗️  Building frontend for $STAGE..."
cd "$PROJECT_DIR/frontend"
[ -f .env.dev ] && cp .env.dev .env
VITE_AUTH_MODE=cognito VITE_API_URL=/api npm run build
cd "$PROJECT_DIR"

# ── Step 3: CDK deploy ──────────────────────────────────────────────────
echo "☁️  Deploying CDK stacks (stage=$STAGE, region=$REGION)..."
cd "$PROJECT_DIR/infra"
export AGENT_RUNTIME_ID="$AGENT_RUNTIME_ID"
JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 \
CDK_DEFAULT_REGION="$REGION" cdk deploy --all \
  --context stage="$STAGE" \
  --require-approval never \
  --outputs-file "$PROJECT_DIR/cdk-outputs-$STAGE.json"
cd "$PROJECT_DIR"

# ── Step 4: Deploy agent to AgentCore Runtime ───────────────────────────
echo "🚀 Deploying agent to AgentCore Runtime ($AGENT_NAME)..."
DEPLOY_TS=$(date -u +%Y%m%d%H%M%S)
uv run agentcore deploy --agent "$AGENT_NAME" \
  --env MESSAGES_TABLE="$MESSAGES_TABLE" \
  --env SESSIONS_TABLE="$SESSIONS_TABLE" \
  --env UPLOAD_BUCKET="$UPLOAD_BUCKET" \
  --env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
  --env BEDROCK_REGION="$REGION" \
  --env DEPLOY_TS="$DEPLOY_TS" \
  -auc

# ── Step 5: Re-apply AgentCore runtime config ───────────────────────────
# agentcore deploy wipes authorizerConfiguration and requestHeaderConfiguration
echo "🔑 Restoring AgentCore runtime config (JWT authorizer + header allowlist)..."
aws bedrock-agentcore-control update-agent-runtime \
  --agent-runtime-id "$AGENT_RUNTIME_ID" --region "$REGION" \
  --role-arn "$EXECUTION_ROLE" \
  --network-configuration '{"networkMode": "PUBLIC"}' \
  --agent-runtime-artifact "{\"codeConfiguration\":{\"code\":{\"s3\":{\"bucket\":\"$S3_BUCKET\",\"prefix\":\"$AGENT_NAME/deployment.zip\"}},\"runtime\":\"PYTHON_3_13\",\"entryPoint\":[\"opentelemetry-instrument\",\"agent/runtime_app.py\"]}}" \
  --authorizer-configuration "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$COGNITO_DISCOVERY_URL\",\"allowedAudience\":[\"$COGNITO_AUDIENCE\"]}}" \
  --request-header-configuration '{"requestHeaderAllowlist":["Authorization"]}' \
  --environment-variables "{\"MESSAGES_TABLE\":\"$MESSAGES_TABLE\",\"SESSIONS_TABLE\":\"$SESSIONS_TABLE\",\"UPLOAD_BUCKET\":\"$UPLOAD_BUCKET\"}" \
  --output text --query "status"

echo "⏳ Waiting for runtime to be READY..."
aws bedrock-agentcore-control wait agent-runtime-ready \
  --agent-runtime-id "$AGENT_RUNTIME_ID" --region "$REGION" 2>/dev/null || \
  sleep 20  # fallback if wait not available

STATUS=$(aws bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id "$AGENT_RUNTIME_ID" --region "$REGION" \
  --query "status" --output text)
echo "   Runtime status: $STATUS"

# ── Step 6: CloudFront invalidation ─────────────────────────────────────
if [ -n "$CF_DISTRIBUTION_ID" ]; then
  echo "🌐 Invalidating CloudFront cache..."
  aws cloudfront create-invalidation \
    --distribution-id "$CF_DISTRIBUTION_ID" \
    --paths "/*" --region us-east-1 --output text --query "Invalidation.Id"
fi

echo ""
echo "✅ Dev deploy complete ($REGION)"
echo "   Agent: $AGENT_NAME ($AGENT_RUNTIME_ID)"
echo "   CDK outputs: cdk-outputs-$STAGE.json"
