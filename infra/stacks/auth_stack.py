"""Cognito stack — User Pool + Client for JWT authentication."""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_cognito as cognito,
)
from constructs import Construct


class AuthStack(Stack):
    def __init__(self, scope: Construct, id: str, frontend_url: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── User Pool ────────────────────────────────────────────────────────
        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="storyteller-users",
            self_sign_up_enabled=False,  # Admin-only registration
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Enable Managed Login UI (Essentials tier for OAuth2)
        cfn_user_pool = self.user_pool.node.default_child
        cfn_user_pool.add_property_override("UserPoolTier", "ESSENTIALS")

        # ── Hosted UI domain ─────────────────────────────────────────────────
        self.domain = self.user_pool.add_domain(
            "UserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"storyteller-{self.account}",
            ),
        )

        # ── App Client (public — no secret for SPA) ─────────────────────────
        self.user_pool_client = self.user_pool.add_client(
            "SpaClient",
            user_pool_client_name="storyteller-spa",
            generate_secret=False,  # Public client for web apps
            auth_flows=cognito.AuthFlow(
                admin_user_password=True,
                user_password=True,
                user_srp=True,
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=[
                    frontend_url,
                    f"{frontend_url}/callback.html",
                    "http://localhost:5173",
                    "http://localhost:5173/callback.html",
                ],
                logout_urls=[
                    frontend_url,
                    "http://localhost:5173",
                ],
            ),
            id_token_validity=Duration.hours(1),
            access_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),
        )

        # ── OIDC discovery URL (for AgentCore JWT authorizer) ────────────────
        self.oidc_discovery_url = (
            f"https://cognito-idp.{self.region}.amazonaws.com/"
            f"{self.user_pool.user_pool_id}/.well-known/openid-configuration"
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        CfnOutput(
            self,
            "CognitoDomain",
            value=self.domain.base_url(),
        )
        CfnOutput(self, "OidcDiscoveryUrl", value=self.oidc_discovery_url)
