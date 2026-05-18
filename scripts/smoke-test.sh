#!/bin/bash
# smoke-test.sh — Quick post-deploy smoke test: login + one message
# Usage: ./scripts/smoke-test.sh [dev|prod]
# Verifies:
#   1. Cognito login works (gets token)
#   2. /sessions endpoint responds (Lambda health)
#   3. /chat-stream responds with agent output (AgentCore runtime health)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

STAGE="${1:-dev}"
ENV_FILE="$PROJECT_DIR/.env.$STAGE"

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ $ENV_FILE not found"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

echo "🔥 Smoke test — $STAGE"
echo ""

# ── Step 1: Login ──────────────────────────────────────────────────────────
echo "1️⃣  Logging in..."

if [ "$STAGE" = "prod" ]; then
  echo "   ⚠️  Prod uses federate auth — skipping Cognito login, using API key"
  # For prod, we'd need a different auth mechanism. Skip for now.
  echo "   TODO: implement prod smoke test auth"
  exit 0
fi

# Extract pool ID from discovery URL if not set directly
if [ -z "${COGNITO_POOL_ID:-}" ] && [ -z "${VITE_COGNITO_POOL_ID:-}" ]; then
  POOL_ID=$(echo "${COGNITO_DISCOVERY_URL:-}" | grep -oP 'us-[a-z]+-[0-9]_[A-Za-z0-9]+' | head -1)
else
  POOL_ID="${COGNITO_POOL_ID:-${VITE_COGNITO_POOL_ID:-}}"
fi
CLIENT_ID="${COGNITO_CLIENT_ID:-${VITE_COGNITO_CLIENT_ID:-${COGNITO_AUDIENCE:-}}}"
REGION="${VITE_COGNITO_REGION:-${CDK_DEFAULT_REGION:-us-west-2}}"
TEST_EMAIL="${SMOKE_TEST_EMAIL:-e2e-test@storyteller.dev}"
TEST_PASSWORD="${SMOKE_TEST_PASSWORD:-Test6e6b80e86e571fb1!1}"

TOKEN=$(aws cognito-idp admin-initiate-auth \
  --user-pool-id "$POOL_ID" \
  --client-id "$CLIENT_ID" \
  --auth-flow ADMIN_USER_PASSWORD_AUTH \
  --auth-parameters "USERNAME=$TEST_EMAIL,PASSWORD=$TEST_PASSWORD" \
  --region "$REGION" \
  --query 'AuthenticationResult.IdToken' \
  --output text 2>&1)

if [[ "$TOKEN" == *"error"* ]] || [[ "$TOKEN" == *"Error"* ]]; then
  echo "   ❌ Login failed: $TOKEN"
  exit 1
fi
echo "   ✅ Login OK (token length: ${#TOKEN})"

# ── Step 2: Sessions endpoint ──────────────────────────────────────────────
echo ""
echo "2️⃣  Testing /sessions endpoint..."

API_URL="${API_URL:-${VITE_API_URL:-}}"
HTTP_CODE=$(curl -s -o /tmp/smoke-sessions.json -w "%{http_code}" \
  "$API_URL/sessions" \
  -H "Authorization: Bearer $TOKEN")

if [ "$HTTP_CODE" != "200" ]; then
  echo "   ❌ /sessions returned HTTP $HTTP_CODE"
  cat /tmp/smoke-sessions.json
  exit 1
fi
SESSION_COUNT=$(python3 -c "import json; print(len(json.load(open('/tmp/smoke-sessions.json')).get('sessions', [])))")
echo "   ✅ /sessions OK ($SESSION_COUNT sessions)"

# ── Step 3: Chat message ──────────────────────────────────────────────────
echo ""
echo "3️⃣  Sending test message to agent..."

SESSION_ID="smoke-test-$(date +%s)"
RESPONSE=$(curl -s -N --max-time 60 -X POST "$API_URL/chat-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"שלום, רק בדיקה קצרה. תגיד שלום.\", \"session_id\": \"$SESSION_ID\"}")

# Check for errors
if echo "$RESPONSE" | grep -q '"error"'; then
  echo "   ❌ Agent error:"
  echo "$RESPONSE" | grep "error"
  exit 1
fi

# Check we got actual streamed data
DATA_LINES=$(echo "$RESPONSE" | grep -c '^data: ' || true)
if [ "$DATA_LINES" -lt 1 ]; then
  echo "   ❌ No streamed data received"
  echo "   Raw response: $RESPONSE"
  exit 1
fi

# Extract text
AGENT_TEXT=$(echo "$RESPONSE" | grep '^data: ' | sed 's/^data: //' | tr -d '"' | tr -d '\n' | sed 's/__PROGRESS__[^}]*}//g' | sed 's/__KEEPALIVE__//g')
echo "   ✅ Agent responded: ${AGENT_TEXT:0:100}..."

# ── Step 4: Check memory session manager (from logs) ──────────────────────
echo ""
echo "4️⃣  Checking memory integration..."

sleep 3
AGENT_RUNTIME_ID="${AGENT_RUNTIME_ID:-}"
if [ -n "$AGENT_RUNTIME_ID" ]; then
  MEMORY_LOG=$(aws logs tail "/aws/bedrock-agentcore/runtimes/$AGENT_RUNTIME_ID-DEFAULT" \
    --region "$REGION" --since 1m --format short \
    --log-stream-name-prefix "$(date -u +%Y/%m/%d)/[runtime-logs" 2>&1 | \
    grep "$SESSION_ID" | grep -i "session.manager\|memory\|Created event\|No session manager" | tail -3)

  if echo "$MEMORY_LOG" | grep -q "Created event"; then
    echo "   ✅ Memory events written"
  elif echo "$MEMORY_LOG" | grep -q "No session manager"; then
    echo "   ⚠️  Session manager NOT active (memory not writing)"
  else
    echo "   ℹ️  Could not determine memory status from logs"
  fi
fi

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "🎉 Smoke test PASSED ($STAGE)"
