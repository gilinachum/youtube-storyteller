"""AgentCore Gateway stack — Web Search Tool connector target.

Backs agent/tools/web_research.py, which calls this gateway's WebSearch
MCP tool in place of the previous Tavily integration. Perplexity
(agent/tools/trend_analysis.py) is unaffected and continues to call
api.perplexity.ai directly — it was deliberately kept for its synthesized-
answer behavior, which the Web Search Tool connector does not provide.

Region pin: the Web Search Tool connector is us-east-1-only today (see
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-connector-web-search-tool.md#gateway-target-connector-web-search-tool-availability).
This stack is deployed to us-east-1 regardless of stage (dev runs its
primary stack in us-west-2, prod in us-east-1) — see infra/app.py wiring.
Both stages' AgentCore runtime roles call across region into this single
shared gateway.
"""
import aws_cdk as cdk
from aws_cdk import aws_bedrockagentcore as bac
from aws_cdk import aws_iam as iam
from constructs import Construct


class GatewaySearchStack(cdk.Stack):
    """Gateway + Web Search Tool target, shared by dev and prod stages.

    Grants `bedrock-agentcore:InvokeGateway` to the given runtime role ARNs
    so the storyteller agent (running in either region) can call this
    gateway's WebSearch MCP tool via SigV4.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        prefix: str,
        invoker_role_arns: list[str],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        invoker_role_arns = [arn for arn in invoker_role_arns if arn]

        # Execution role AgentCore assumes to call the Web Search backend on
        # our behalf. Built manually (rather than letting the L2 Gateway
        # construct auto-create one) so we control the exact policy per the
        # connector docs: InvokeGateway (scoped to this gateway) +
        # InvokeWebSearch (scoped to the service-owned web-search tool ARN).
        gateway_role = iam.Role(
            self,
            "GatewayExecutionRole",
            role_name=f"{prefix}-gateway-search-role",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/*"
                    },
                },
            ),
        )
        gateway_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeGateway",
                actions=["bedrock-agentcore:InvokeGateway"],
                resources=[f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:gateway/*"],
            )
        )
        gateway_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeWebSearch",
                actions=["bedrock-agentcore:InvokeWebSearch"],
                # Service-owned ARN, region-scoped but account replaced with
                # "aws" (not the caller's account). The public devguide page
                # shows this ARN with an EMPTY region segment
                # (arn:aws:bedrock-agentcore::aws:tool/web-search.v1), which
                # is WRONG and causes "Execution role is not authorized for
                # connector web-search" at tools/call time even though the
                # policy attaches cleanly. Every working sample (AWS's own
                # AgiInfoWebToolSamples Setup-CLI-IAM.md / Setup-SDK-IAM.md)
                # fills in the region. Verified by hand-testing both forms
                # against a live gateway.
                resources=[f"arn:aws:bedrock-agentcore:{self.region}:aws:tool/web-search.v1"],
            )
        )

        gateway = bac.Gateway(
            self,
            "Gateway",
            gateway_name=f"{prefix}-search-gateway",
            description="Web Search Tool target backing agent/tools/web_research.py",
            role=gateway_role,
            authorizer_configuration=bac.GatewayAuthorizer.using_aws_iam(),
        )

        # No L2 factory for connector targets yet (for_lambda/for_open_api/
        # for_smithy/for_api_gateway/for_mcp_server exist, but not
        # for_connector) — use the L1 CfnGatewayTarget directly with the
        # exact connector shape from the AWS docs.
        target = bac.CfnGatewayTarget(
            self,
            "WebSearchTarget",
            gateway_identifier=gateway.gateway_id,
            name="web-search-tool",
            target_configuration=bac.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bac.CfnGatewayTarget.McpTargetConfigurationProperty(
                    connector=bac.CfnGatewayTarget.ConnectorTargetConfigurationProperty(
                        source=bac.CfnGatewayTarget.ConnectorSourceProperty(
                            connector_id="web-search"
                        ),
                        configurations=[
                            bac.CfnGatewayTarget.ConnectorConfigurationProperty(
                                name="WebSearch",
                                parameter_values={},
                            )
                        ],
                    )
                )
            ),
            credential_provider_configurations=[
                bac.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                    credential_provider_type="GATEWAY_IAM_ROLE"
                )
            ],
        )
        target.node.add_dependency(gateway)

        # Grant each storyteller runtime role permission to invoke this
        # gateway. Kept here (not on the runtime stacks) so "who can call
        # this gateway" stays colocated with the gateway definition.
        for i, arn in enumerate(invoker_role_arns):
            invoker = iam.Role.from_role_arn(self, f"InvokerRole{i}", arn)
            gateway.grant_invoke(invoker)

        self.gateway_url = gateway.gateway_url
        self.gateway_id = gateway.gateway_id

        cdk.CfnOutput(self, "GatewayUrl", value=gateway.gateway_url)
        cdk.CfnOutput(self, "GatewayId", value=gateway.gateway_id)
