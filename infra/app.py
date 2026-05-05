"""StoryTeller CDK app entrypoint.

Usage:
    cdk deploy --all --context stage=dev    # us-west-2, Cognito auth
    cdk deploy --all --context stage=prod   # us-east-1, Federate auth (overlay)
"""
import os
import aws_cdk as cdk
from stacks.data_stack import DataStack
from stacks.api_stack import ApiStack
from stacks.frontend_stack import FrontendStack
from stacks.backup_stack import BackupStack

app = cdk.App()

stage = app.node.try_get_context("stage") or os.environ.get("STAGE", "dev")

CONFIG = {
    "dev": {
        "region": "us-west-2",
        "prefix": "storyteller-dev",
        "auth_mode": "cognito",
        "agentcore_memory_id": "storytellerDevMemory-rStdOCAQvm",
        "runtime_role_arn": "arn:aws:iam::726941381086:role/AmazonBedrockAgentCoreSDKRuntime-us-west-2-9bda7c8513",
    },
    "prod": {
        "region": "us-east-1",
        "prefix": "storyteller",
        "stack_prefix": "StoryTeller",  # match existing CFN stack names
        "auth_mode": "federate",  # Federate OIDC auth for prod
        "agentcore_memory_id": "",  # TODO: add prod memory ID when created
        "runtime_role_arn": "arn:aws:iam::726941381086:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-2a5e1ea1dc",
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
    agentcore_memory_id=cfg.get("agentcore_memory_id", ""),
    runtime_role_arn=cfg.get("runtime_role_arn", ""),
    env=env,
)

frontend = FrontendStack(app, f"{sp}Frontend" if sp[0].isupper() else f"{cfg['prefix']}-frontend",
    uploads_bucket_arn=data.uploads_bucket.bucket_arn,
    api=api.api,
    prefix=cfg["prefix"],
    env=env,
)
frontend.add_dependency(api)

# ── Backup stack (DynamoDB daily snapshots) ──────────────────────────────
account = os.environ.get("CDK_DEFAULT_ACCOUNT", "726941381086")
table_arns = [
    f"arn:aws:dynamodb:{cfg['region']}:{account}:table/{cfg['prefix']}-sessions",
    f"arn:aws:dynamodb:{cfg['region']}:{account}:table/{cfg['prefix']}-messages",
    f"arn:aws:dynamodb:{cfg['region']}:{account}:table/{cfg['prefix']}-jobs",
]
backup_stack = BackupStack(app, f"{cfg['prefix']}-backup",
    prefix=cfg["prefix"],
    table_arns=table_arns,
    env=env,
)

cdk.Tags.of(app).add("Project", "StoryTeller")
cdk.Tags.of(app).add("Stage", stage)
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()
