"""StoryTeller CDK app entrypoint."""
import os
import aws_cdk as cdk
from stacks.data_stack import DataStack
from stacks.api_stack import ApiStack
from stacks.frontend_stack import FrontendStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

data     = DataStack(app, "StoryTellerData", env=env)
api      = ApiStack(app, "StoryTellerApi", data_stack=data, env=env)
frontend = FrontendStack(app, "StoryTellerFrontend",
    uploads_bucket_arn=data.uploads_bucket.bucket_arn,
    api=api.api,
    env=env,
)
frontend.add_dependency(api)

cdk.Tags.of(app).add("Project", "StoryTeller")
cdk.Tags.of(app).add("ManagedBy", "CDK")

app.synth()
