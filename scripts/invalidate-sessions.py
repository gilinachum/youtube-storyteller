#!/usr/bin/env python3
"""Force-restart all AgentCore Runtime agent processes after a deploy.

Since the runtime uses JWT auth for session operations (stop_runtime_session),
and we can't easily call that as an admin, we instead trigger a no-op config
update which forces AgentCore to recycle all cached processes.

Usage:
    python scripts/invalidate-sessions.py           # Force restart
    python scripts/invalidate-sessions.py --wait    # Wait until READY
"""
import argparse
import os
import sys
import time

import boto3

# Load .env.{stage}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
stage = os.environ.get("STAGE", "dev")
env_file = os.path.join(PROJECT_DIR, f".env.{stage}")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

REGION = os.environ.get("AWS_REGION", "us-west-2")


def find_runtime():
    """Find the AgentCore runtime for the current stage."""
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    runtimes = client.list_agent_runtimes().get("agentRuntimes", [])
    for rt in runtimes:
        rt_id = rt.get("agentRuntimeId", "")
        if stage.lower() in rt_id.lower():
            return rt_id, client
    if len(runtimes) == 1:
        return runtimes[0]["agentRuntimeId"], client
    print(f"ERROR: Could not find runtime for stage={stage}.")
    print(f"Available: {[r['agentRuntimeId'] for r in runtimes]}")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Force-restart AgentCore Runtime processes")
    parser.add_argument("--wait", action="store_true", help="Wait until runtime is READY")
    args = parser.parse_args()

    runtime_id, client = find_runtime()
    print(f"Runtime: {runtime_id}")
    print(f"Stage: {stage} | Region: {REGION}\n")

    # Get current config
    current = client.get_agent_runtime(agentRuntimeId=runtime_id)

    # Trigger update with same config (forces process recycle)
    # Add/update a timestamp env var to ensure the update is not a no-op
    env_vars = current.get("environmentVariables", {})
    env_vars["_LAST_INVALIDATION"] = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    print("Triggering runtime update (forces process recycle)...")
    client.update_agent_runtime(
        agentRuntimeId=runtime_id,
        roleArn=current["roleArn"],
        networkConfiguration=current["networkConfiguration"],
        agentRuntimeArtifact=current["agentRuntimeArtifact"],
        environmentVariables=env_vars,
        authorizerConfiguration=current.get("authorizerConfiguration", {}),
        requestHeaderConfiguration=current.get("requestHeaderConfiguration", {}),
    )

    if args.wait:
        print("Waiting for READY...", end="", flush=True)
        for i in range(60):
            time.sleep(2)
            status = client.get_agent_runtime(agentRuntimeId=runtime_id)["status"]
            if status == "READY":
                print(f" ✅ READY ({(i+1)*2}s)")
                return
            print(".", end="", flush=True)
        print(" ⚠️ Timeout (120s)")
        sys.exit(1)
    else:
        print("✅ Update triggered. Processes will recycle within ~30s.")
        print("   Run with --wait to block until READY.")


if __name__ == "__main__":
    main()
