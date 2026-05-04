#!/bin/bash
# deploy-prod.sh — Deploy StoryTeller to prod environment (us-east-1, Federate/CFS auth)
#
# This script:
# 1. Ensures the private overlay is applied
# 2. Builds frontend with prod config (Federate auth)
# 3. Deploys CDK stacks with stage=prod
# 4. Deploys agent to AgentCore Runtime
# 5. Re-applies AgentCore runtime config (Federate JWT authorizer + header allowlist)
# 6. Applies CFS protection (Midway)
# 7. Invalidates CloudFront cache
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

STAGE="prod"
REGION="us-east-1"
PREFIX="storyteller"
AGENT_NAME="storyteller"

echo "🔧 [$STAGE] Deploying StoryTeller to $REGION..."

# ── Load env ────────────────────────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/.env.prod" ]; then
  echo "❌ Missing .env.prod — copy from .env.example and fill in prod values"
  exit 1
fi
set -a; source "$PROJECT_DIR/.env.prod"; set +a

# Required vars
AGENT_RUNTIME_ID="${AGENT_RUNTIME_ID:?Set AGENT_RUNTIME_ID in .env}"
EXECUTION_ROLE="${EXECUTION_ROLE:-arn:aws:iam::726941381086:role/AmazonBedrockAgentCoreSDKRuntime-$REGION-2a5e1ea1dc}"
FEDERATE_DISCOVERY_URL="${FEDERATE_DISCOVERY_URL:-https://idp.federate.amazon.com/.well-known/openid-configuration}"
FEDERATE_AUDIENCE="${FEDERATE_AUDIENCE:-storyteller-cognito}"
MESSAGES_TABLE="${MESSAGES_TABLE:-$PREFIX-messages}"
SESSIONS_TABLE="${SESSIONS_TABLE:-$PREFIX-sessions}"
UPLOAD_BUCKET="${UPLOAD_BUCKET:?Set UPLOAD_BUCKET in .env}"
CF_DISTRIBUTION_ID="${CF_DISTRIBUTION_ID:-}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-6}"
S3_BUCKET="bedrock-agentcore-codebuild-sources-726941381086-$REGION"

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

# ── Step 2: Build frontend ──────────────────────────────────────────────
echo "🏗️  Building frontend for $STAGE..."
cd "$PROJECT_DIR/frontend"
[ -f .env.prod ] && cp .env.prod .env
VITE_AUTH_MODE=federate VITE_API_URL=/api npm run build
cd "$PROJECT_DIR"

# ── Step 3: CDK deploy ──────────────────────────────────────────────────
echo "☁️  Deploying CDK stacks (stage=$STAGE, region=$REGION)..."
cd "$PROJECT_DIR/infra"
export AGENT_RUNTIME_ID="$AGENT_RUNTIME_ID"
JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 \
CDK_DEFAULT_REGION="$REGION" cdk deploy --all \
  --context stage="$STAGE" \
  --context agentcoreMemoryId="${AGENTCORE_MEMORY_ID:-}" \
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
  --env AGENTCORE_MEMORY_ID="${AGENTCORE_MEMORY_ID:-}" \
  --env JOBS_TABLE="${JOBS_TABLE:-storyteller-jobs}" \
  --env DEPLOY_TS="$DEPLOY_TS" \
  -auc

# ── Step 5: Re-apply AgentCore runtime config ───────────────────────────
# agentcore deploy wipes authorizerConfiguration and requestHeaderConfiguration
echo "🔑 Restoring AgentCore runtime config (Federate JWT authorizer + header allowlist)..."
aws bedrock-agentcore-control update-agent-runtime \
  --agent-runtime-id "$AGENT_RUNTIME_ID" --region "$REGION" \
  --role-arn "$EXECUTION_ROLE" \
  --network-configuration '{"networkMode": "PUBLIC"}' \
  --agent-runtime-artifact "{\"codeConfiguration\":{\"code\":{\"s3\":{\"bucket\":\"$S3_BUCKET\",\"prefix\":\"$AGENT_NAME/deployment.zip\"}},\"runtime\":\"PYTHON_3_13\",\"entryPoint\":[\"opentelemetry-instrument\",\"agent/runtime_app.py\"]}}" \
  --authorizer-configuration "{\"customJWTAuthorizer\":{\"discoveryUrl\":\"$FEDERATE_DISCOVERY_URL\",\"allowedAudience\":[\"$FEDERATE_AUDIENCE\"]}}" \
  --request-header-configuration '{"requestHeaderAllowlist":["Authorization"]}' \
  --environment-variables "{\"MESSAGES_TABLE\":\"$MESSAGES_TABLE\",\"SESSIONS_TABLE\":\"$SESSIONS_TABLE\",\"UPLOAD_BUCKET\":\"$UPLOAD_BUCKET\",\"AGENTCORE_MEMORY_ID\":\"${AGENTCORE_MEMORY_ID:-}\",\"JOBS_TABLE\":\"${JOBS_TABLE:-storyteller-jobs}\"}" \
  --output text --query "status"

echo "⏳ Waiting for runtime to be READY..."
aws bedrock-agentcore-control wait agent-runtime-ready \
  --agent-runtime-id "$AGENT_RUNTIME_ID" --region "$REGION" 2>/dev/null || \
  sleep 20  # fallback if wait not available

STATUS=$(aws bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id "$AGENT_RUNTIME_ID" --region "$REGION" \
  --query "status" --output text)
echo "   Runtime status: $STATUS"

# ── Step 6: CFS protection (Midway) ────────────────────────────────────
if [ -f "$PROJECT_DIR/infra-private/setup_midway.py" ]; then
  echo "🛡️  Applying CFS protection..."
  uv run python3 "$PROJECT_DIR/infra-private/setup_midway.py"
else
  echo "⏭️  Skipping CFS setup (infra-private/setup_midway.py not found)"
fi

# ── Step 7: CloudFront invalidation ─────────────────────────────────────
if [ -n "$CF_DISTRIBUTION_ID" ]; then
  echo "🌐 Invalidating CloudFront cache..."
  aws cloudfront create-invalidation \
    --distribution-id "$CF_DISTRIBUTION_ID" \
    --paths "/*" --region us-east-1 --output text --query "Invalidation.Id"
fi

echo ""
echo "✅ Prod deploy complete ($REGION)"
echo "   Agent: $AGENT_NAME ($AGENT_RUNTIME_ID)"
echo "   CDK outputs: cdk-outputs-$STAGE.json"
