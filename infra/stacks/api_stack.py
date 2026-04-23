"""API stack — API Gateway + Lambda functions + AgentCore streaming."""
import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_cognito as cognito,
)
from constructs import Construct
from stacks.data_stack import DataStack
from stacks.auth_stack import AuthStack

# Path to the project root (one level up from infra/)
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


class ApiStack(Stack):
    def __init__(self, scope: Construct, id: str, data_stack: DataStack, auth_stack: AuthStack, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── Shared Lambda role with base permissions ─────────────────────────
        lambda_role = iam.Role(
            self, "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        # Secrets Manager read (all storyteller secrets)
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[
                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:firecrawl/api-key*",
                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:perplexity/api-key*",
                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:tavily/api-key*",
            ],
        ))

        # Bedrock InvokeModel for Claude
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"],
        ))

        # DynamoDB full access to our tables
        data_stack.sessions_table.grant_read_write_data(lambda_role)
        data_stack.messages_table.grant_read_write_data(lambda_role)

        # S3 access to uploads bucket
        data_stack.uploads_bucket.grant_read_write(lambda_role)

        # Amazon Transcribe access
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "transcribe:StartTranscriptionJob",
                "transcribe:GetTranscriptionJob",
                "transcribe:DeleteTranscriptionJob",
            ],
            resources=["*"],
        ))

        # ── Common Lambda environment ────────────────────────────────────────
        common_env = {
            "SESSIONS_TABLE": data_stack.sessions_table.table_name,
            "MESSAGES_TABLE": data_stack.messages_table.table_name,
            "UPLOAD_BUCKET": data_stack.uploads_bucket.bucket_name,
            "AWS_ACCOUNT_ID": self.account,
            "POWERTOOLS_SERVICE_NAME": "storyteller",
        }

        # ── Auth Lambda ──────────────────────────────────────────────────────
        auth_fn = lambda_.Function(
            self, "AuthFn",
            function_name="storyteller-auth",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="auth.handler",
            code=lambda_.Code.from_asset(os.path.join(PROJECT_ROOT, "api")),
            timeout=Duration.seconds(10),
            memory_size=128,
            role=lambda_role,
            environment=common_env,
        )

        # ── Sessions Lambda ──────────────────────────────────────────────────
        sessions_fn = lambda_.Function(
            self, "SessionsFn",
            function_name="storyteller-sessions",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="sessions.handler",
            code=lambda_.Code.from_asset(os.path.join(PROJECT_ROOT, "api")),
            timeout=Duration.seconds(30),
            memory_size=256,
            role=lambda_role,
            environment=common_env,
        )

        # ── Upload Lambda ────────────────────────────────────────────────────
        upload_fn = lambda_.Function(
            self, "UploadFn",
            function_name="storyteller-upload",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="upload.handler",
            code=lambda_.Code.from_asset(os.path.join(PROJECT_ROOT, "api")),
            timeout=Duration.seconds(30),
            memory_size=256,
            role=lambda_role,
            environment=common_env,
        )

        # ── API Gateway ──────────────────────────────────────────────────────
        api = apigw.RestApi(
            self, "StoryTellerApi",
            rest_api_name="storyteller-api",
            description="StoryTeller YouTube planning agent API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization", "X-Session-Token"],
            ),
        )

        # POST /auth/verify
        auth_resource = api.root.add_resource("auth").add_resource("verify")
        auth_resource.add_method("POST", apigw.LambdaIntegration(auth_fn))

        # GET /sessions  +  GET /sessions/{id}
        sessions_resource = api.root.add_resource("sessions")
        sessions_resource.add_method("GET", apigw.LambdaIntegration(sessions_fn))
        sessions_id_resource = sessions_resource.add_resource("{id}")
        sessions_id_resource.add_method("GET", apigw.LambdaIntegration(sessions_fn))

        # POST /sessions/{id}/share
        share_resource = sessions_id_resource.add_resource("share")
        share_resource.add_method("POST", apigw.LambdaIntegration(sessions_fn))

        # GET /sessions/{id}/files/{file_id}
        files_resource = sessions_id_resource.add_resource("files")
        file_id_resource = files_resource.add_resource("{file_id}")
        file_id_resource.add_method("GET", apigw.LambdaIntegration(sessions_fn))


        # POST /upload
        upload_resource = api.root.add_resource("upload")
        upload_resource.add_method("POST", apigw.LambdaIntegration(upload_fn))
        upload_resource.add_method("GET", apigw.LambdaIntegration(upload_fn))
        upload_resource.add_method("DELETE", apigw.LambdaIntegration(upload_fn))

        # ── Transcribe Lambda ────────────────────────────────────────────────
        transcribe_fn = lambda_.Function(
            self, "TranscribeFn",
            function_name="storyteller-transcribe",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="transcribe.handler",
            code=lambda_.Code.from_asset(os.path.join(PROJECT_ROOT, "api")),
            timeout=Duration.seconds(60),  # Transcribe can take up to ~30s
            memory_size=256,
            role=lambda_role,
            environment=common_env,
        )

        # POST /transcribe
        transcribe_resource = api.root.add_resource("transcribe")
        transcribe_resource.add_method("POST", apigw.LambdaIntegration(transcribe_fn))

        # ── AgentCore Runtime Streaming Integration (JWT auth) ─────────────
        # POST /chat-stream → AgentCore Runtime /invocations (streaming)
        # API GW validates Cognito JWT, then passes it through to Runtime
        # Runtime validates the same JWT (defense in depth)
        RUNTIME_ID = self.node.try_get_context("agentRuntimeId") or os.environ.get("AGENT_RUNTIME_ID", "")
        RUNTIME_ENDPOINT = (
            f"https://bedrock-agentcore.{self.region}.amazonaws.com"
            f"/runtimes/{RUNTIME_ID}/invocations"
            f"?qualifier=DEFAULT&accountId={self.account}"
        )

        # Cognito authorizer — validates ID tokens at the API GW layer
        cognito_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "CognitoAuthorizer",
            cognito_user_pools=[auth_stack.user_pool],
        )

        # HTTP Proxy Integration — passes request straight to Runtime
        # The Authorization header is forwarded so Runtime's JWT authorizer
        # can validate it too (defense in depth)
        runtime_integration = apigw.HttpIntegration(
            RUNTIME_ENDPOINT,
            http_method="POST",
            proxy=True,
            options=apigw.IntegrationOptions(
                connection_type=apigw.ConnectionType.INTERNET,
                timeout=Duration.minutes(15),  # streaming allows up to 15 min
                request_parameters={
                    "integration.request.header.Authorization":
                        "method.request.header.Authorization",
                    "integration.request.header.Content-Type":
                        "'application/json'",
                },
            ),
        )

        # POST /chat-stream with Cognito auth
        chat_stream_resource = api.root.add_resource("chat-stream")
        stream_method = chat_stream_resource.add_method(
            "POST",
            runtime_integration,
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO,
            request_parameters={
                "method.request.header.Authorization": True,
            },
        )

        # CRITICAL: Enable response streaming (escape hatch — CDK doesn't expose this)
        cfn_method = stream_method.node.default_child
        cfn_method.add_property_override("Integration.ResponseTransferMode", "STREAM")

        # ── Outputs ──────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "ApiUrl", value=api.url)
        cdk.CfnOutput(self, "StreamEndpoint", value=f"{api.url}chat-stream")
