#!/bin/bash
# deploy.sh — Deploy agent to AgentCore Runtime.
#
# No JWT authorizer on the runtime by default (anyone who can reach it
# can invoke it). For production, add your own JWT provider via the
# customJWTAuthorizer configuration.
#
# Required env vars (or set in .env):
#   AGENT_RUNTIME_ID  — AgentCore Runtime ID
#   MESSAGES_TABLE    — DynamoDB messages table name
#   SESSIONS_TABLE    — DynamoDB sessions table name
#   UPLOAD_BUCKET     — S3 upload bucket name
#   BEDROCK_MODEL_ID  — Bedrock model ID (default: us.anthropic.claude-sonnet-4-6)
#   BEDROCK_REGION    — Bedrock region (default: us-east-1)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

AGENT_RUNTIME_ID="${AGENT_RUNTIME_ID:?Set AGENT_RUNTIME_ID env var}"
REGION="${BEDROCK_REGION:-us-east-1}"
MESSAGES_TABLE="${MESSAGES_TABLE:?Set MESSAGES_TABLE env var}"
SESSIONS_TABLE="${SESSIONS_TABLE:?Set SESSIONS_TABLE env var}"
UPLOAD_BUCKET="${UPLOAD_BUCKET:?Set UPLOAD_BUCKET env var}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-6}"

echo "🚀 Deploying agent to AgentCore Runtime..."
DEPLOY_TS=$(date -u +%Y%m%d%H%M%S)
uv run agentcore deploy \
  --env MESSAGES_TABLE="$MESSAGES_TABLE" \
  --env SESSIONS_TABLE="$SESSIONS_TABLE" \
  --env UPLOAD_BUCKET="$UPLOAD_BUCKET" \
  --env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
  --env BEDROCK_REGION="$REGION" \
  --env DEPLOY_TS="$DEPLOY_TS" \
  -auc

echo ""
echo "✅ Deploy complete. Start a new session to use updated agent."
