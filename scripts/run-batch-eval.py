#!/usr/bin/env python3
"""Run AgentCore batch evaluation on StoryTeller sessions.

Evaluates historical agent sessions using LLM-as-Judge built-in evaluators.
Reads OTEL traces from CloudWatch Logs and scores each session.

Usage:
    # Evaluate last 7 days (default)
    python scripts/run-batch-eval.py

    # Evaluate last N days
    python scripts/run-batch-eval.py --days 14

    # Evaluate specific sessions
    python scripts/run-batch-eval.py --sessions 2bc13a7b-a858-4ab4-a145-f42ec78e6014

    # Custom evaluators
    python scripts/run-batch-eval.py --evaluators GoalSuccessRate Helpfulness

    # Don't wait for results (fire and forget)
    python scripts/run-batch-eval.py --no-wait

Environment:
    Reads from .env.prod (default) or .env.dev (with --stage dev).
    Requires AWS credentials with bedrock-agentcore and logs permissions.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Load env file
def load_env(stage: str):
    env_file = Path(__file__).parent.parent / f".env.{stage}"
    if not env_file.exists():
        print(f"❌ {env_file} not found")
        sys.exit(1)
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main():
    parser = argparse.ArgumentParser(description="Run AgentCore batch evaluation on StoryTeller")
    parser.add_argument("--stage", default="prod", choices=["dev", "prod"], help="Environment (default: prod)")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    parser.add_argument("--sessions", nargs="+", help="Specific session IDs to evaluate")
    parser.add_argument("--evaluators", nargs="+", default=["GoalSuccessRate", "Helpfulness", "ToolSelectionAccuracy"],
                        help="Evaluator names (without Builtin. prefix)")
    parser.add_argument("--no-wait", action="store_true", help="Start job and exit without waiting")
    parser.add_argument("--name", help="Custom evaluation name (auto-generated if not set)")
    args = parser.parse_args()

    load_env(args.stage)

    import boto3

    # Resolve config from env
    region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
    runtime_id = os.environ.get("AGENT_RUNTIME_ID", "")

    if not runtime_id:
        print("❌ AGENT_RUNTIME_ID not set in environment")
        sys.exit(1)

    log_group = f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT"
    # Service name follows AgentCore convention: {runtime_name}.{endpoint}
    # The runtime name is the part before the random suffix
    runtime_name = runtime_id.rsplit("-", 1)[0] if "-" in runtime_id else runtime_id
    service_name = f"{runtime_name}.DEFAULT"

    # Build evaluator list
    evaluators = [{"evaluatorId": f"Builtin.{e}" if not e.startswith("Builtin.") else e}
                  for e in args.evaluators]

    # Build filter config
    filter_config = {}
    if args.sessions:
        filter_config["sessionIds"] = args.sessions
    else:
        now = datetime.now(timezone.utc)
        filter_config["timeRange"] = {
            "startTime": (now - timedelta(days=args.days)).isoformat(),
            "endTime": now.isoformat(),
        }

    # Build data source
    data_source = {
        "cloudWatchLogs": {
            "serviceNames": [service_name],
            "logGroupNames": [log_group],
        }
    }
    if filter_config:
        data_source["cloudWatchLogs"]["filterConfig"] = filter_config

    # Generate job name
    eval_name = args.name or f"storyteller_{args.stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    # Ensure valid pattern: starts with letter, alphanumeric + underscores, max 48 chars
    eval_name = eval_name[:48]

    print(f"🔬 Starting batch evaluation")
    print(f"   Stage:      {args.stage}")
    print(f"   Region:     {region}")
    print(f"   Log group:  {log_group}")
    print(f"   Service:    {service_name}")
    print(f"   Evaluators: {[e['evaluatorId'] for e in evaluators]}")
    if args.sessions:
        print(f"   Sessions:   {args.sessions}")
    else:
        print(f"   Time range: last {args.days} days")
    print(f"   Job name:   {eval_name}")
    print()

    client = boto3.client("bedrock-agentcore", region_name=region)

    try:
        response = client.start_batch_evaluation(
            batchEvaluationName=eval_name,
            evaluators=evaluators,
            dataSourceConfig=data_source,
            clientToken=str(uuid.uuid4()),
        )
    except Exception as e:
        print(f"❌ Failed to start batch evaluation: {e}")
        sys.exit(1)

    batch_id = response["batchEvaluationId"]
    print(f"✅ Batch evaluation started: {batch_id}")
    print(f"   ARN: {response.get('batchEvaluationArn', 'N/A')}")
    print(f"   Status: {response.get('status', 'PENDING')}")

    if args.no_wait:
        print(f"\n   Run again with: python scripts/run-batch-eval.py --stage {args.stage}")
        print(f"   Or check status: aws bedrock-agentcore get-batch-evaluation --batch-evaluation-id {batch_id} --region {region}")
        return

    # Poll for results
    print(f"\n⏳ Waiting for completion (polling every 30s)...")
    start_time = time.time()

    while True:
        time.sleep(30)
        elapsed = int(time.time() - start_time)

        try:
            result = client.get_batch_evaluation(batchEvaluationId=batch_id)
        except Exception as e:
            print(f"   [{elapsed}s] Error polling: {e}")
            continue

        status = result.get("status", "UNKNOWN")
        print(f"   [{elapsed}s] Status: {status}")

        if status in ("COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "STOPPED"):
            break

        if elapsed > 600:  # 10 min timeout
            print(f"\n⚠️  Timed out after {elapsed}s. Job still running.")
            print(f"   Check later: aws bedrock-agentcore get-batch-evaluation --batch-evaluation-id {batch_id} --region {region}")
            return

    # Display results
    print(f"\n{'='*60}")
    print(f"📊 Batch Evaluation Results")
    print(f"{'='*60}")
    print(f"   Status: {result.get('status')}")
    print(f"   Sessions evaluated: {result.get('totalSessionCount', 'N/A')}")

    # Print per-evaluator scores
    summaries = result.get("evaluationSummaries", result.get("evaluatorResults", []))
    if summaries:
        print(f"\n   {'Evaluator':<30} {'Avg Score':<12} {'Sessions'}")
        print(f"   {'-'*30} {'-'*12} {'-'*10}")
        for s in summaries:
            name = s.get("evaluatorId", s.get("evaluator", "?"))
            score = s.get("averageScore", s.get("score", "N/A"))
            count = s.get("sessionCount", s.get("evaluatedSessions", "N/A"))
            if isinstance(score, float):
                print(f"   {name:<30} {score:<12.3f} {count}")
            else:
                print(f"   {name:<30} {score:<12} {count}")
    else:
        print("\n   (No summary data in response — check CloudWatch for per-session results)")

    # Save full response
    output_dir = Path(__file__).parent.parent / "evaluations"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{eval_name}.json"
    output_file.write_text(json.dumps(result, indent=2, default=str))
    print(f"\n   Full results saved to: {output_file}")


if __name__ == "__main__":
    main()
