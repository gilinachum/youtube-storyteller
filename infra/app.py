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

app = cdk.App()

stage = app.node.try_get_context("stage") or os.environ.get("STAGE", "dev")

CONFIG = {
    "dev": {
        "region": "us-west-2",
        "prefix": "storyteller-dev",
        "auth_mode": "cognito",
    },
    "prod": {
        "region": "us-east-1",
        "prefix": "storyteller",
        "auth_mode": "none",  # prod overlay replaces this file with federate auth
    },
}

if stage not in CONFIG:
    raise ValueError(f"Unknown stage '{stage}'. Valid: {list(CONFIG.keys())}")

cfg = CONFIG[stage]
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=cfg["region"],  # stage controls region, not env var
)

data = DataStack(app, f"{cfg['prefix']}-data",
    prefix=cfg["prefix"],
    env=env,
)

api = ApiStack(app, f"{cfg['prefix']}-api",
    data_stack=data,
    auth_mode=cfg["auth_mode"],
    prefix=cfg["prefix"],
    env=env,
)

frontend = FrontendStack(app, f"{cfg['prefix']}-frontend",
    uploads_bucket_arn=data.uploads_bucket.bucket_arn,
    api=api.api,
    prefix=cfg["prefix"],
    env=env,
)
frontend.add_dependency(api)

cdk.Tags.of(app).add("Project", "StoryTeller")
cdk.Tags.of(app).add("Stage", stage)
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()
