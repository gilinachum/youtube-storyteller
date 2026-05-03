"""API stack — API Gateway + Lambda functions + AgentCore streaming.

Auth mode:
  - "cognito": Cognito User Pool authorizer (dev)
  - "none": No authorizer — identity from request body (default/public)
  - The prod overlay replaces this file entirely with Federate auth.
"""
import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_iam as iam,
)
from constructs import Construct
from stacks.data_stack import DataStack

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


class ApiStack(Stack):
    def __init__(self, scope: Construct, id: str,
                 data_stack: DataStack,
                 auth_mode: str = "none",
                 prefix: str = "storyteller",
                 **kwargs):
        super().__init__(scope, id, **kwargs)

        self.auth_mode = auth_mode

        # ── Shared Lambda role ──────────────────────────────────────────────
        lambda_role = iam.Role(
            self, "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[
                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:firecrawl/api-key*",
                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:perplexity/api-key*",
                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:tavily/api-key*",
            ],
        ))
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=["*"],
        ))
        data_stack.sessions_table.grant_read_write_data(lambda_role)
        data_stack.messages_table.grant_read_write_data(lambda_role)
        data_stack.uploads_bucket.grant_read_write(lambda_role)
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "transcribe:StartTranscriptionJob",
                "transcribe:GetTranscriptionJob",
                "transcribe:DeleteTranscriptionJob",
            ],
            resources=["*"],
        ))

        # ── Common Lambda env ────────────────────────────────────────────────
        common_env = {
            "SESSIONS_TABLE": data_stack.sessions_table.table_name,
            "MESSAGES_TABLE": data_stack.messages_table.table_name,
            "UPLOAD_BUCKET":  data_stack.uploads_bucket.bucket_name,
            "AWS_ACCOUNT_ID": self.account,
            "POWERTOOLS_SERVICE_NAME": prefix,
        }

        # ── Lambda factory ──────────────────────────────────────────────────
        def _mk_fn(name: str, handler: str, timeout: int = 30, memory: int = 256) -> lambda_.Function:
            return lambda_.Function(
                self, name + "Fn",
                function_name=f"{prefix}-{name.lower()}",
                runtime=lambda_.Runtime.PYTHON_3_13,
                architecture=lambda_.Architecture.ARM_64,
                handler=handler,
                code=lambda_.Code.from_asset(os.path.join(PROJECT_ROOT, "api")),
                timeout=Duration.seconds(timeout),
                memory_size=memory,
                role=lambda_role,
                environment=common_env,
            )

        sessions_fn   = _mk_fn("Sessions",   "sessions.handler")
        upload_fn     = _mk_fn("Upload",      "upload.handler")
        transcribe_fn = _mk_fn("Transcribe",  "transcribe.handler")

        # ── Cognito User Pool (dev auth) ────────────────────────────────────
        authorizer = None
        default_auth: dict = {}

        if auth_mode == "cognito":
            self.user_pool = cognito.UserPool(
                self, "UserPool",
                user_pool_name=f"{prefix}-users",
                self_sign_up_enabled=False,
                sign_in_aliases=cognito.SignInAliases(email=True),
                password_policy=cognito.PasswordPolicy(
                    min_length=8,
                    require_uppercase=False,
                    require_symbols=False,
                ),
                removal_policy=cdk.RemovalPolicy.DESTROY,
            )

            self.user_pool_client = self.user_pool.add_client(
                "WebClient",
                auth_flows=cognito.AuthFlow(
                    user_password=True,
                    user_srp=True,
                ),
                generate_secret=False,
            )

            authorizer = apigw.CognitoUserPoolsAuthorizer(
                self, "CognitoAuth",
                cognito_user_pools=[self.user_pool],
            )

            default_auth = {
                "authorizer": authorizer,
                "authorization_type": apigw.AuthorizationType.COGNITO,
            }

            cdk.CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
            cdk.CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)

        # ── API Gateway ──────────────────────────────────────────────────────
        api = apigw.RestApi(
            self, "StoryTellerApi",
            rest_api_name=f"{prefix}-api",
            description=f"StoryTeller API ({auth_mode} auth)",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization", "X-Session-Token"],
            ),
        )
        self.api = api

        # Sessions
        sessions_res   = api.root.add_resource("sessions")
        sessions_res.add_method("GET", apigw.LambdaIntegration(sessions_fn), **default_auth)
        session_id_res = sessions_res.add_resource("{id}")
        session_id_res.add_method("GET",    apigw.LambdaIntegration(sessions_fn), **default_auth)
        session_id_res.add_method("DELETE", apigw.LambdaIntegration(sessions_fn), **default_auth)
        share_res = session_id_res.add_resource("share")
        share_res.add_method("POST", apigw.LambdaIntegration(sessions_fn), **default_auth)
        files_res = session_id_res.add_resource("files")
        file_id_res = files_res.add_resource("{file_id}")
        file_id_res.add_method("GET", apigw.LambdaIntegration(sessions_fn), **default_auth)

        # Upload
        upload_res = api.root.add_resource("upload")
        upload_res.add_method("POST",   apigw.LambdaIntegration(upload_fn), **default_auth)
        upload_res.add_method("GET",    apigw.LambdaIntegration(upload_fn), **default_auth)
        upload_res.add_method("DELETE", apigw.LambdaIntegration(upload_fn), **default_auth)

        # Transcribe
        transcribe_res = api.root.add_resource("transcribe")
        transcribe_res.add_method("POST", apigw.LambdaIntegration(transcribe_fn), **default_auth)
        job_res = transcribe_res.add_resource("{job_name}")
        job_res.add_method("GET", apigw.LambdaIntegration(transcribe_fn), **default_auth)

        # ── AgentCore Runtime streaming ─────────────────────────────────────
        RUNTIME_ID = self.node.try_get_context("agentRuntimeId") or os.environ.get("AGENT_RUNTIME_ID", "")
        RUNTIME_ENDPOINT = (
            f"https://bedrock-agentcore.{self.region}.amazonaws.com"
            f"/runtimes/{RUNTIME_ID}/invocations"
            f"?qualifier=DEFAULT&accountId={self.account}"
        )
        runtime_integration = apigw.HttpIntegration(
            RUNTIME_ENDPOINT,
            http_method="POST",
            proxy=True,
            options=apigw.IntegrationOptions(
                connection_type=apigw.ConnectionType.INTERNET,
                timeout=Duration.minutes(15),
                request_parameters={
                    "integration.request.header.Content-Type": "'application/json'",
                },
            ),
        )
        chat_stream_res = api.root.add_resource("chat-stream")
        stream_method = chat_stream_res.add_method(
            "POST",
            runtime_integration,
            **default_auth,
        )
        cfn_method = stream_method.node.default_child
        cfn_method.add_property_override("Integration.ResponseTransferMode", "STREAM")

        # ── Outputs ──────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "ApiUrl", value=api.url)
        cdk.CfnOutput(self, "RestApiId", value=api.rest_api_id)
        cdk.CfnOutput(self, "StreamEndpoint", value=f"{api.url}chat-stream")
