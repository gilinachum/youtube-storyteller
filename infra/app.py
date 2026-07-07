"""StoryTeller CDK app entrypoint.

Usage (via deploy script only):
    scripts/deploy.sh dev
    scripts/deploy.sh prod

Direct `cdk deploy` is blocked — use the deploy script which handles
AgentCore, JWT auth restore, CFS protection, and frontend deployment.
"""
import os
import sys
from pathlib import Path
import aws_cdk as cdk

# Guard: prevent direct `cdk deploy` without the deploy script.
# CDK calls `python3 app.py` for ALL subcommands (synth, diff, deploy, etc.)
# so we can't detect which one. Instead:
#   - deploy.sh sets STORYTELLER_DEPLOY_SCRIPT=1 (allows everything)
#   - For read-only (synth/diff): set STORYTELLER_CDK_READONLY=1
#   - Neither set = block (prevents accidental `cdk deploy`)
_has_deploy_bypass = os.environ.get("STORYTELLER_DEPLOY_SCRIPT") == "1"
_has_readonly_bypass = os.environ.get("STORYTELLER_CDK_READONLY") == "1"

if not _has_deploy_bypass and not _has_readonly_bypass:
    print("\n" + "=" * 60)
    print("❌ ERROR: Do not run `cdk deploy` directly!")
    print("=" * 60)
    print("")
    print("Use the deploy script instead:")
    print("  scripts/deploy.sh dev")
    print("  scripts/deploy.sh prod")
    print("")
    print("Why? The deploy script handles:")
    print("  • AgentCore agent deployment")
    print("  • JWT auth restore (CDK resets TrustedKeyGroups)")
    print("  • CFS/Midway protection re-application")
    print("  • Frontend build + S3 sync + CloudFront invalidation")
    print("")
    print("For read-only operations (synth/diff):")
    print("  STORYTELLER_CDK_READONLY=1 cdk synth --context stage=dev")
    print("  STORYTELLER_CDK_READONLY=1 cdk diff --context stage=dev")
    print("=" * 60 + "\n")
    sys.exit(1)
from stacks.data_stack import DataStack
from stacks.api_stack import ApiStack
from stacks.frontend_stack import FrontendStack
from stacks.backup_stack import BackupStack
from stacks.evaluations_stack import EvaluationsStack

app = cdk.App()

stage = app.node.try_get_context("stage") or os.environ.get("STAGE", "dev")

# Load .env.{stage} file into os.environ (so CDK picks up config without shell sourcing)
_env_file = Path(__file__).parent.parent / f".env.{stage}"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

CONFIG = {
    "dev": {
        "region": "us-west-2",
        "prefix": "storyteller-dev",
        "auth_mode": "cognito",
    },
    "prod": {
        "region": "us-east-1",
        "prefix": "storyteller",
        "stack_prefix": "StoryTeller",  # match existing CFN stack names
        "auth_mode": "federate",  # Federate OIDC auth for prod
    },
}

if stage not in CONFIG:
    raise ValueError(f"Unknown stage '{stage}'. Valid: {list(CONFIG.keys())}")

cfg = CONFIG[stage]
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=cfg["region"],  # stage controls region, not env var
)

sp = cfg.get('stack_prefix', cfg['prefix'])

data = DataStack(app, f"{sp}Data" if sp[0].isupper() else f"{cfg['prefix']}-data",
    prefix=cfg["prefix"],
    env=env,
)

api = ApiStack(app, f"{sp}Api" if sp[0].isupper() else f"{cfg['prefix']}-api",
    data_stack=data,
    auth_mode=cfg["auth_mode"],
    prefix=cfg["prefix"],
    env=env,
)

frontend = FrontendStack(app, f"{sp}Frontend" if sp[0].isupper() else f"{cfg['prefix']}-frontend",
    uploads_bucket_arn=data.uploads_bucket.bucket_arn,
    api=api.api,
    prefix=cfg["prefix"],
    cfs_key_group_id=os.environ.get("CFS_KEY_GROUP_ID", ""),
    env=env,
)
frontend.add_dependency(api)

# ── Backup stack (DynamoDB daily snapshots) ──────────────────────────────
account = os.environ.get("CDK_DEFAULT_ACCOUNT", "726941381086")
table_arns = [
    f"arn:aws:dynamodb:{cfg['region']}:{account}:table/storyteller-sessions",
    f"arn:aws:dynamodb:{cfg['region']}:{account}:table/storyteller-messages",
    f"arn:aws:dynamodb:{cfg['region']}:{account}:table/storyteller-jobs",
]
backup_stack = BackupStack(app, f"{cfg['prefix']}-backup",
    prefix=cfg["prefix"],
    table_arns=table_arns,
    env=env,
)

# ── Evaluations stack (AgentCore online evaluation) ─────────────────────
runtime_id = os.environ.get("AGENT_RUNTIME_ID", "")
if runtime_id:
    evaluations_stack = EvaluationsStack(app, f"{sp}Evaluations" if sp[0].isupper() else f"{cfg['prefix']}-evaluations",
        prefix=cfg["prefix"],
        runtime_id=runtime_id,
        sampling_percentage=100.0,
        env=env,
    )

cdk.Tags.of(app).add("Project", "StoryTeller")
cdk.Tags.of(app).add("Stage", stage)
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()
