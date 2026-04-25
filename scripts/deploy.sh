#!/bin/bash
# deploy.sh — Deploy agent to AgentCore Runtime + restore JWT auth
# Usage: ./scripts/deploy.sh
#
# Required env vars (or set in .env):
#   AGENT_RUNTIME_ID        — AgentCore Runtime ID
#   COGNITO_DISCOVERY_URL   — Cognito OIDC discovery URL
#   COGNITO_AUDIENCE        — Cognito app client ID
#   MESSAGES_TABLE          — DynamoDB messages table name
#   SESSIONS_TABLE          — DynamoDB sessions table name
#   UPLOAD_BUCKET           — S3 upload bucket name
#   BEDROCK_MODEL_ID        — Bedrock model ID (default: us.anthropic.claude-sonnet-4-6)
#   BEDROCK_REGION          — Bedrock region (default: us-east-1)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

AGENT_RUNTIME_ID="${AGENT_RUNTIME_ID:?Set AGENT_RUNTIME_ID env var}"
REGION="${BEDROCK_REGION:-us-east-1}"
COGNITO_DISCOVERY_URL="${COGNITO_DISCOVERY_URL:?Set COGNITO_DISCOVERY_URL env var}"
COGNITO_AUDIENCE="${COGNITO_AUDIENCE:?Set COGNITO_AUDIENCE env var}"
MESSAGES_TABLE="${MESSAGES_TABLE:?Set MESSAGES_TABLE env var}"
SESSIONS_TABLE="${SESSIONS_TABLE:?Set SESSIONS_TABLE env var}"
UPLOAD_BUCKET="${UPLOAD_BUCKET:?Set UPLOAD_BUCKET env var}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-sonnet-4-6}"

echo "🚀 Deploying agent to AgentCore Runtime..."
uv run agentcore deploy \
  --env MESSAGES_TABLE="$MESSAGES_TABLE" \
  --env SESSIONS_TABLE="$SESSIONS_TABLE" \
  --env UPLOAD_BUCKET="$UPLOAD_BUCKET" \
  --env BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
  --env BEDROCK_REGION="$REGION" \
  -auc

echo ""
echo "🔐 Restoring JWT authorizer (deploy resets it)..."
uv run python3 << PYEOF
import boto3
client = boto3.client("bedrock-agentcore-control", region_name="${REGION}")
current = client.get_agent_runtime(agentRuntimeId="${AGENT_RUNTIME_ID}")
client.update_agent_runtime(
    agentRuntimeId="${AGENT_RUNTIME_ID}",
    roleArn=current["roleArn"],
    networkConfiguration=current["networkConfiguration"],
    agentRuntimeArtifact=current["agentRuntimeArtifact"],
    environmentVariables=current.get("environmentVariables", {}),
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "discoveryUrl": "${COGNITO_DISCOVERY_URL}",
            "allowedAudience": ["${COGNITO_AUDIENCE}"]
        }
    }
)
print("✅ JWT auth restored")
PYEOF

echo ""
echo "✅ Deploy complete. Start a new session to use updated agent."
