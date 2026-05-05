"""API stack — API Gateway + Lambda functions + AgentCore streaming.

Unified auth: supports both Cognito (dev) and Federate OIDC (prod)
based on the auth_mode parameter.
"""
from __future__ import annotations

import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_secretsmanager as sm,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct
from stacks.data_stack import DataStack

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
LAYERS_DIR = os.path.join(os.path.dirname(__file__), "..", "layers")


class ApiStack(Stack):
    def __init__(self, scope: Construct, id: str,
                 data_stack: DataStack,
                 auth_mode: str = "cognito",
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
        # AgentCore Memory permissions
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock-agentcore:CreateEvent",
                "bedrock-agentcore:ListEvents",
                "bedrock-agentcore:GetEvent",
                "bedrock-agentcore:DeleteEvent",
                "bedrock-agentcore:ListSessions",
                "bedrock-agentcore:CreateSession",
                "bedrock-agentcore:GetSession",
            ],
            resources=["*"],
        ))
        data_stack.sessions_table.grant_read_write_data(lambda_role)
        data_stack.messages_table.grant_read_write_data(lambda_role)
        data_stack.jobs_table.grant_read_write_data(lambda_role)
        data_stack.uploads_bucket.grant_read_write(lambda_role)
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "transcribe:StartTranscriptionJob",
                "transcribe:GetTranscriptionJob",
                "transcribe:DeleteTranscriptionJob",
            ],
            resources=["*"],
        ))

        # ── AgentCore Runtime Role — app-level permissions ────────────────
        # The runtime role is created by `agentcore` CLI; we import and attach policy here.
        runtime_role_arn = self.node.try_get_context("agentcoreRuntimeRoleArn") or os.environ.get("EXECUTION_ROLE", "")
        if runtime_role_arn:
            runtime_role = iam.Role.from_role_arn(
                self, "AgentCoreRuntimeRole", runtime_role_arn, mutable=True
            )
            runtime_role.add_to_policy(iam.PolicyStatement(
                sid="SecretsManagerAccess",
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:firecrawl/*",
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:tavily/*",
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:gcp/*",
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:storyteller/*",
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:perplexity/*",
                ],
            ))
            data_stack.uploads_bucket.grant_read_write(runtime_role)
            data_stack.sessions_table.grant_read_write_data(runtime_role)
            data_stack.jobs_table.grant_read_write_data(runtime_role)

        # Transcription handler Lambda name (for job_resolver to invoke)
        transcription_handler_name = f"{prefix}-transcription-handler"

        # ── Common Lambda env ────────────────────────────────────────────────
        common_env = {
            "SESSIONS_TABLE": data_stack.sessions_table.table_name,
            "MESSAGES_TABLE": data_stack.messages_table.table_name,
            "UPLOAD_BUCKET": data_stack.uploads_bucket.bucket_name,
            "JOBS_TABLE": data_stack.jobs_table.table_name,
            "TRANSCRIPTION_HANDLER_FN": transcription_handler_name,
            "AWS_ACCOUNT_ID": self.account,
            "POWERTOOLS_SERVICE_NAME": prefix,
        }

        # AgentCore Memory ID (set via CDK context or env)
        agentcore_memory_id = self.node.try_get_context("agentcoreMemoryId") or os.environ.get("AGENTCORE_MEMORY_ID", "")
        if agentcore_memory_id:
            common_env["AGENTCORE_MEMORY_ID"] = agentcore_memory_id

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

        sessions_fn = _mk_fn("Sessions", "sessions.handler")
        upload_fn = _mk_fn("Upload", "upload.handler")
        transcribe_fn = _mk_fn("Transcribe", "transcribe.handler")

        # Jobs system
        jobs_poll_fn = _mk_fn("JobsPoll", "jobs_poll.handler", timeout=10)

        transcription_handler_fn = lambda_.Function(
            self, "TranscriptionHandlerFn",
            function_name=transcription_handler_name,
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="transcription_handler.handler",
            code=lambda_.Code.from_asset(os.path.join(PROJECT_ROOT, "api")),
            timeout=Duration.seconds(300),
            memory_size=512,
            role=lambda_role,
            environment=common_env,
        )

        job_resolver_fn = _mk_fn("JobResolver", "job_resolver.handler", timeout=60)
        # Grant invoke on transcription handler — use hardcoded ARN to avoid
        # circular dependency (both functions share lambda_role)
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:{transcription_handler_name}"],
        ))

        # EventBridge rule: fire job resolver every minute
        events.Rule(
            self, "JobResolverSchedule",
            rule_name=f"{prefix}-job-resolver",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            targets=[targets.LambdaFunction(job_resolver_fn)],
        )

        # ── Auth setup (mode-dependent) ──────────────────────────────────────
        authorizer = None
        default_auth: dict = {}
        auth_callback_fn = None

        if auth_mode == "cognito":
            # ── Cognito User Pool (dev) ─────────────────────────────────────
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

        elif auth_mode == "federate":
            # ── Federate OIDC (prod) ────────────────────────────────────────
            # Config from CDK context or env vars
            federate_issuer = self.node.try_get_context("federateIssuer") or os.environ.get("FEDERATE_ISSUER", "https://idp.federate.amazon.com")
            federate_jwks_uri = self.node.try_get_context("federateJwksUri") or os.environ.get("FEDERATE_JWKS_URI", "https://idp.federate.amazon.com/api/oauth2/v2/certs")
            federate_token_url = self.node.try_get_context("federateTokenUrl") or os.environ.get("FEDERATE_TOKEN_URL", "https://idp.federate.amazon.com/api/oauth2/v2/token")
            federate_audience = self.node.try_get_context("federateAudience") or os.environ.get("FEDERATE_AUDIENCE", "storyteller-cognito")
            federate_allowed_group = self.node.try_get_context("federateAllowedGroup") or os.environ.get("FEDERATE_ALLOWED_GROUP", "")

            # Federate OIDC client secret (created manually, imported here)
            federate_secret = sm.Secret.from_secret_name_v2(
                self, "FederateSecret", "federate/storyteller-cognito",
            )

            # Shared PyJWT layer (ARM64 Python 3.13)
            jwt_layer = lambda_.LayerVersion(
                self, "PyJwtLayer",
                code=lambda_.Code.from_asset(os.path.join(LAYERS_DIR, "federate-auth")),
                compatible_runtimes=[lambda_.Runtime.PYTHON_3_13],
                compatible_architectures=[lambda_.Architecture.ARM_64],
                description="PyJWT[crypto] for Federate token validation",
            )

            # Auth-specific role (needs the Federate secret)
            auth_role = iam.Role(
                self, "AuthLambdaRole",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                ],
            )
            federate_secret.grant_read(auth_role)

            # Federate JWT authorizer Lambda
            authorizer_fn = lambda_.Function(
                self, "FederateAuthorizerFn",
                function_name=f"{prefix}-federate-authorizer",
                runtime=lambda_.Runtime.PYTHON_3_13,
                architecture=lambda_.Architecture.ARM_64,
                handler="federate_authorizer.handler",
                code=lambda_.Code.from_asset(os.path.join(PROJECT_ROOT, "api")),
                timeout=Duration.seconds(10),
                memory_size=256,
                role=auth_role,
                layers=[jwt_layer],
                environment={
                    "FEDERATE_ISSUER": federate_issuer,
                    "FEDERATE_JWKS_URI": federate_jwks_uri,
                    "FEDERATE_AUDIENCE": federate_audience,
                    "FEDERATE_ALLOWED_GROUP": federate_allowed_group,
                },
            )
            authorizer = apigw.TokenAuthorizer(
                self, "FederateAuthorizer",
                handler=authorizer_fn,
                identity_source="method.request.header.Authorization",
                results_cache_ttl=Duration.minutes(5),
            )

            default_auth = {
                "authorizer": authorizer,
                "authorization_type": apigw.AuthorizationType.CUSTOM,
            }

            # Auth-callback Lambda (code→token exchange)
            auth_callback_fn = lambda_.Function(
                self, "AuthCallbackFn",
                function_name=f"{prefix}-auth-callback",
                runtime=lambda_.Runtime.PYTHON_3_13,
                architecture=lambda_.Architecture.ARM_64,
                handler="auth_callback.handler",
                code=lambda_.Code.from_asset(os.path.join(PROJECT_ROOT, "api")),
                timeout=Duration.seconds(15),
                memory_size=256,
                role=auth_role,
                environment={
                    "FEDERATE_TOKEN_URL": federate_token_url,
                    "FEDERATE_SECRET_ARN": federate_secret.secret_arn,
                },
            )

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

        # Auth callback route (Federate only — unauthenticated)
        if auth_callback_fn is not None:
            auth_res = api.root.add_resource("auth")
            callback_res = auth_res.add_resource("callback")
            callback_res.add_method(
                "POST",
                apigw.LambdaIntegration(auth_callback_fn),
                authorization_type=apigw.AuthorizationType.NONE,
            )

        # Sessions
        sessions_res = api.root.add_resource("sessions")
        sessions_res.add_method("GET", apigw.LambdaIntegration(sessions_fn), **default_auth)
        session_id_res = sessions_res.add_resource("{id}")
        session_id_res.add_method("GET", apigw.LambdaIntegration(sessions_fn), **default_auth)
        session_id_res.add_method("DELETE", apigw.LambdaIntegration(sessions_fn), **default_auth)
        share_res = session_id_res.add_resource("share")
        share_res.add_method("POST", apigw.LambdaIntegration(sessions_fn), **default_auth)
        files_res = session_id_res.add_resource("files")
        file_id_res = files_res.add_resource("{file_id}")
        file_id_res.add_method("GET", apigw.LambdaIntegration(sessions_fn), **default_auth)

        # Upload
        upload_res = api.root.add_resource("upload")
        upload_res.add_method("POST", apigw.LambdaIntegration(upload_fn), **default_auth)
        upload_res.add_method("GET", apigw.LambdaIntegration(upload_fn), **default_auth)
        upload_res.add_method("DELETE", apigw.LambdaIntegration(upload_fn), **default_auth)

        # Transcribe
        transcribe_res = api.root.add_resource("transcribe")
        transcribe_res.add_method("POST", apigw.LambdaIntegration(transcribe_fn), **default_auth)
        job_res = transcribe_res.add_resource("{job_name}")
        job_res.add_method("GET", apigw.LambdaIntegration(transcribe_fn), **default_auth)

        # /jobs/poll — lightweight job status polling endpoint
        jobs_res = api.root.add_resource("jobs")
        jobs_poll_res = jobs_res.add_resource("poll")
        jobs_poll_res.add_method("GET", apigw.LambdaIntegration(jobs_poll_fn), **default_auth)

        # ── AgentCore Runtime streaming ──────────────────────────────────────
        RUNTIME_ID = self.node.try_get_context("agentRuntimeId") or os.environ.get("AGENT_RUNTIME_ID", "")
        if RUNTIME_ID:
            RUNTIME_ENDPOINT = (
                f"https://bedrock-agentcore.{self.region}.amazonaws.com"
                f"/runtimes/{RUNTIME_ID}/invocations"
                f"?qualifier=DEFAULT&accountId={self.account}"
            )

            # Always forward Authorization header to AgentCore Runtime
            # (so the agent can extract email from the JWT)
            request_params = {
                "integration.request.header.Content-Type": "'application/json'",
                "integration.request.header.Authorization": "method.request.header.Authorization",
            }

            runtime_integration = apigw.HttpIntegration(
                RUNTIME_ENDPOINT,
                http_method="POST",
                proxy=True,
                options=apigw.IntegrationOptions(
                    connection_type=apigw.ConnectionType.INTERNET,
                    timeout=Duration.minutes(15),  # STREAM mode supports up to 15min
                    request_parameters=request_params,
                ),
            )

            chat_stream_res = api.root.add_resource("chat-stream")

            if auth_mode == "federate":
                # Federate: authorizer validates JWT, pass Authorization header through
                stream_method = chat_stream_res.add_method(
                    "POST",
                    runtime_integration,
                    authorizer=authorizer,
                    authorization_type=apigw.AuthorizationType.CUSTOM,
                    request_parameters={"method.request.header.Authorization": True},
                )
            elif auth_mode == "cognito":
                # Cognito: API GW validates token via Cognito authorizer
                stream_method = chat_stream_res.add_method(
                    "POST",
                    runtime_integration,
                    **default_auth,
                    request_parameters={"method.request.header.Authorization": True},
                )
            else:
                # No auth
                stream_method = chat_stream_res.add_method(
                    "POST",
                    runtime_integration,
                    authorization_type=apigw.AuthorizationType.NONE,
                )

            cfn_method = stream_method.node.default_child
            cfn_method.add_property_override("Integration.ResponseTransferMode", "STREAM")
            cdk.CfnOutput(self, "StreamEndpoint", value=f"{api.url}chat-stream")

        # ── Outputs ──────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "ApiUrl", value=api.url)
        cdk.CfnOutput(self, "RestApiId", value=api.rest_api_id)
