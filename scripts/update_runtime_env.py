#!/usr/bin/env python3
"""Safe AgentCore runtime env var updater.

Reads current config, applies env var changes, preserves ALL other fields
(authorizerConfiguration, requestHeaderConfiguration, etc).

Usage:
    # Set/update env vars:
    python3 scripts/update_runtime_env.py BEDROCK_REGION=us-west-2 UPLOAD_BUCKET=my-bucket

    # Remove env vars:
    python3 scripts/update_runtime_env.py --remove MESSAGES_TABLE SESSIONS_TABLE

    # Both:
    python3 scripts/update_runtime_env.py BEDROCK_REGION=us-west-2 --remove OLD_VAR
"""
import sys
import os
import boto3
import json

# Load .env.dev for defaults
ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env.dev")
if os.path.exists(ENV_FILE):
    for line in open(ENV_FILE):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

REGION = os.environ.get("BEDROCK_REGION", os.environ.get("CDK_DEFAULT_REGION", "us-west-2"))
RUNTIME_ID = os.environ.get("AGENT_RUNTIME_ID", "storytellerDev-qd6NXW9wC8")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    set_vars = {}
    remove_vars = []
    removing = False

    for arg in args:
        if arg == "--remove":
            removing = True
            continue
        if removing:
            remove_vars.append(arg)
        elif "=" in arg:
            k, _, v = arg.partition("=")
            set_vars[k] = v
        else:
            print(f"Error: '{arg}' is not KEY=VALUE. Use --remove to delete vars.")
            sys.exit(1)

    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # Read current state (CRITICAL: we must preserve all fields)
    current = client.get_agent_runtime(agentRuntimeId=RUNTIME_ID)

    env = dict(current.get("environmentVariables", {}))
    env.update(set_vars)
    for k in remove_vars:
        env.pop(k, None)

    # Build update kwargs — preserve ALL existing config
    update_kwargs = {
        "agentRuntimeId": RUNTIME_ID,
        "roleArn": current["roleArn"],
        "networkConfiguration": current["networkConfiguration"],
        "agentRuntimeArtifact": current["agentRuntimeArtifact"],
        "environmentVariables": env,
    }

    # Preserve auth config (THE CRITICAL PART — omitting = wiping!)
    if "authorizerConfiguration" in current:
        update_kwargs["authorizerConfiguration"] = current["authorizerConfiguration"]
    if "requestHeaderConfiguration" in current:
        update_kwargs["requestHeaderConfiguration"] = current["requestHeaderConfiguration"]
    if "lifecycleConfiguration" in current:
        update_kwargs["lifecycleConfiguration"] = current["lifecycleConfiguration"]

    client.update_agent_runtime(**update_kwargs)

    print(f"✅ Runtime {RUNTIME_ID} updated")
    if set_vars:
        print(f"   Set: {', '.join(f'{k}={v}' for k, v in set_vars.items())}")
    if remove_vars:
        print(f"   Removed: {', '.join(remove_vars)}")


if __name__ == "__main__":
    main()
