#!/bin/bash
# check-agent.sh — Verify agent runtime status, JWT auth, and env vars
# Usage: ./scripts/check-agent.sh
set -euo pipefail

AGENT_RUNTIME_ID="${AGENT_RUNTIME_ID}"
REGION="us-east-1"

python3 << PYEOF
import boto3, json

client = boto3.client("bedrock-agentcore-control", region_name="${REGION}")
rt = client.get_agent_runtime(agentRuntimeId="${AGENT_RUNTIME_ID}")

status = rt.get("status", "UNKNOWN")
auth = rt.get("authorizerConfiguration")
env_vars = rt.get("environmentVariables", {})

print(f"Status: {status}")
print(f"Auth:   {'✅ JWT configured' if auth else '❌ NO AUTH'}")
print(f"Env:    {len(env_vars)} vars: {', '.join(env_vars.keys())}")

if status != "READY":
    print(f"⚠️  Agent is {status}, not READY")
if not auth:
    print("⚠️  JWT authorizer is missing! Run ./scripts/deploy.sh to restore it.")
PYEOF
