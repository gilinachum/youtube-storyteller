"""StoryTeller CDK app entrypoint."""
import os
import aws_cdk as cdk
from stacks.data_stack import DataStack
from stacks.auth_stack import AuthStack
from stacks.api_stack import ApiStack
from stacks.frontend_stack import FrontendStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

# Resolved from CDK context or environment
FRONTEND_URL = app.node.try_get_context("frontendUrl") or os.environ.get("FRONTEND_URL", "")

data     = DataStack(app, "StoryTellerData", env=env)
auth     = AuthStack(app, "StoryTellerAuth", frontend_url=FRONTEND_URL, env=env)
api      = ApiStack(app, "StoryTellerApi", data_stack=data, auth_stack=auth, env=env)
frontend = FrontendStack(app, "StoryTellerFrontend", env=env)

cdk.Tags.of(app).add("Project", "StoryTeller")
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()
