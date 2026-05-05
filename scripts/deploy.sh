#!/bin/bash
# deploy.sh — Unified deploy script for StoryTeller (dev + prod)
#
# Usage:
#   ./scripts/deploy.sh dev       # Deploy dev (Cognito auth, us-west-2)
#   ./scripts/deploy.sh prod      # Deploy prod (Federate auth, us-east-1)
#   ./scripts/deploy.sh --stage dev
#   ./scripts/deploy.sh --stage prod
#
# NO overlay swap. NO git stash. NO skip-worktree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ── Parse stage argument ─────────────────────────────────────────────────────
STAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage) STAGE="$2"; shift 2 ;;
    dev|prod) STAGE="$1"; shift ;;
    *) echo "❌ Unknown argument: $1"; echo "Usage: $0 [dev|prod|--stage dev|prod]"; exit 1 ;;
  esac
done

if [[ -z "$STAGE" ]]; then
  echo "❌ Stage required. Usage: $0 [dev|prod]"
  exit 1
fi

echo "🚀 Deploying StoryTeller — stage: $STAGE"

# ── Load env file ────────────────────────────────────────────────────────────
ENV_FILE="$PROJECT_DIR/.env.$STAGE"
if [[ -f "$ENV_FILE" ]]; then
  echo "📄 Loading $ENV_FILE"
  set -a
  source "$ENV_FILE"
  set +a
else
  echo "⚠️  No $ENV_FILE found — using existing environment"
fi

# ── Set VITE_AUTH_MODE based on stage ────────────────────────────────────────
if [[ "$STAGE" == "dev" ]]; then
  export VITE_AUTH_MODE="cognito"
elif [[ "$STAGE" == "prod" ]]; then
  export VITE_AUTH_MODE="federate"
  # Verify federate-auth layer exists
  if [[ ! -d "$PROJECT_DIR/infra/layers/federate-auth" ]]; then
    echo "❌ infra/layers/federate-auth/ not found — required for prod (PyJWT layer)"
    exit 1
  fi
fi

echo "🔑 Auth mode: $VITE_AUTH_MODE"

# ── Build frontend ───────────────────────────────────────────────────────────
echo ""
echo "🏗️  Building frontend..."
cd "$PROJECT_DIR/frontend"
npm ci --prefer-offline 2>/dev/null || npm install
npm run build
cd "$PROJECT_DIR"

# ── CDK deploy ───────────────────────────────────────────────────────────────
echo ""
echo "☁️  Deploying CDK stacks (stage=$STAGE)..."
cd "$PROJECT_DIR/infra"
cdk deploy --all --context stage="$STAGE" --require-approval never
cd "$PROJECT_DIR"

# ── AgentCore deploy (if AGENT_RUNTIME_ID is set) ────────────────────────────
AGENT_RUNTIME_ID="${AGENT_RUNTIME_ID:-}"
if [[ -n "$AGENT_RUNTIME_ID" ]]; then
  echo ""
  echo "🤖 Deploying agent to AgentCore Runtime..."
  REGION="${BEDROCK_REGION:-us-east-1}"
  MESSAGES_TABLE="${MESSAGES_TABLE:?Set MESSAGES_TABLE env var}"
  SESSIONS_TABLE="${SESSIONS_TABLE:?Set SESSIONS_TABLE env var}"
  UPLOAD_BUCKET="${UPLOAD_BUCKET:?Set UPLOAD_BUCKET env var}"
  BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-6}"
  DEPLOY_TS=$(date -u +%Y%m%d%H%M%S)

  uv run agentcore deploy \
    --env MESSAGES_TABLE="$MESSAGES_TABLE" \
    --env SESSIONS_TABLE="$SESSIONS_TABLE" \
    --env UPLOAD_BUCKET="$UPLOAD_BUCKET" \
    --env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
    --env BEDROCK_REGION="$REGION" \
    --env DEPLOY_TS="$DEPLOY_TS" \
    -auc

  # ── Restore Federate JWT authorizer (prod only, deploy resets it) ────────
  if [[ "$STAGE" == "prod" ]]; then
    FEDERATE_DISCOVERY_URL="${FEDERATE_DISCOVERY_URL:-https://idp.federate.amazon.com/.well-known/openid-configuration}"
    FEDERATE_AUDIENCE="${FEDERATE_AUDIENCE:-storyteller-cognito}"
    echo ""
    echo "🔐 Restoring Federate JWT authorizer on AgentCore..."
    uv run python3 << PYEOF
import boto3
client = boto3.client("bedrock-agentcore-control", region_name="${REGION}")
current = client.get_agent_runtime(agentRuntimeId="${AGENT_RUNTIME_ID}")
client.update_agent_runtime(
    agentRuntimeId="${AGENT_RUNTIME_ID}",
    roleArn=current["roleArn"],
    networkConfiguration=current["networkConfiguration"],
    agentRuntimeArtifact=current["agentRuntimeArtifact"],
    environmentVariables={**current.get("environmentVariables", {}), "DEPLOY_TS": "${DEPLOY_TS}"},
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "discoveryUrl": "${FEDERATE_DISCOVERY_URL}",
            "allowedAudience": ["${FEDERATE_AUDIENCE}"]
        }
    }
)
print("✅ Federate JWT auth restored")
PYEOF
  fi
else
  echo ""
  echo "ℹ️  AGENT_RUNTIME_ID not set — skipping AgentCore deploy"
fi

# ── CloudFront invalidation ──────────────────────────────────────────────────
DISTRIBUTION_ID="${DISTRIBUTION_ID:-}"
if [[ -n "$DISTRIBUTION_ID" ]]; then
  echo ""
  echo "🌐 Invalidating CloudFront cache..."
  aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*" \
    --query 'Invalidation.Id' --output text
fi

echo ""
echo "✅ Deploy complete ($STAGE)."
