"""Frontend stack — S3 + CloudFront for the React SPA + API origin + media.

CFS (Midway) protection is applied to the default behavior, /api/*, and
/media/* by a separate script (infra-private/setup_midway.py) — it adds
TrustedKeyGroups to these behaviors after the stack is deployed.

The /error/* and /js/cfs-handler.js behaviors stay unrestricted (that's
what serves the CFS auth page itself).
"""
import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cloudfront as cf,
    aws_cloudfront_origins as origins,
    aws_apigateway as apigw,
    RemovalPolicy,
)
from constructs import Construct

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")


class FrontendStack(Stack):
    def __init__(self, scope: Construct, id: str,
                 uploads_bucket_arn: str = "",
                 api = None,  # type: Optional[apigw.RestApi]
                 **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── Frontend bucket (private — served via CloudFront only) ───────────
        bucket = s3.Bucket(
            self, "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        oac = cf.S3OriginAccessControl(self, "OAC", description="StoryTeller frontend OAC")

        # ── SPA path rewrite function (viewer-request) ───────────────────────
        # For any URI without a file extension (e.g. /auth/callback, /chat/xyz),
        # serve /index.html so React Router can handle it client-side.
        spa_rewrite = cf.Function(
            self, "SpaRewrite",
            function_name="storyteller-spa-rewrite",
            code=cf.FunctionCode.from_inline("""
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (!uri.match(/\\.[a-zA-Z0-9]{2,6}$/)) {
    request.uri = '/index.html';
  }
  return request;
}
"""),
            runtime=cf.FunctionRuntime.JS_2_0,
        )

        # ── API prefix strip function (viewer-request for /api/*) ───────────
        # CloudFront sends /api/foo → origin as /api/foo. API Gateway only
        # knows /foo. This function strips /api so the origin sees /foo.
        # (The API stage segment is added automatically by RestApiOrigin.)
        api_rewrite = cf.Function(
            self, "ApiRewrite",
            function_name="storyteller-api-rewrite",
            code=cf.FunctionCode.from_inline("""
function handler(event) {
  var request = event.request;
  if (request.uri.indexOf('/api/') === 0) {
    request.uri = request.uri.substring(4);  // '/api/foo' -> '/foo'
  } else if (request.uri === '/api') {
    request.uri = '/';
  }
  return request;
}
"""),
            runtime=cf.FunctionRuntime.JS_2_0,
        )

        # ── Uploads bucket origin (for /media/*) ─────────────────────────────
        uploads_bucket_ref = s3.Bucket.from_bucket_arn(
            self, "UploadsBucket", uploads_bucket_arn,
        ) if uploads_bucket_arn else None

        media_oac = cf.S3OriginAccessControl(
            self, "MediaOAC", description="StoryTeller media OAC",
        ) if uploads_bucket_ref else None

        additional_behaviors = {}

        # /media/* — served from uploads bucket. CFS protects it via TrustedKeyGroups
        # (added out-of-band by setup_midway.py). No Lambda/Cognito auth anymore.
        if uploads_bucket_ref and media_oac:
            additional_behaviors["/media/*"] = cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    uploads_bucket_ref,
                    origin_access_control=media_oac,
                ),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_OPTIMIZED,
            )

        # /api/* — proxies to API Gateway. CFS cookies gate it at the edge;
        # API Gateway's Federate authorizer validates the Authorization header.
        # api_rewrite strips the '/api' prefix so API GW sees the real path.
        if api is not None:
            api_origin = origins.RestApiOrigin(api)
            additional_behaviors["/api/*"] = cf.BehaviorOptions(
                origin=api_origin,
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                function_associations=[
                    cf.FunctionAssociation(
                        function=api_rewrite,
                        event_type=cf.FunctionEventType.VIEWER_REQUEST,
                    )
                ],
            )

        # ── CloudFront distribution ──────────────────────────────────────────
        distribution = cf.Distribution(
            self, "Distribution",
            comment="StoryTeller frontend",
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    bucket, origin_access_control=oac,
                ),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_OPTIMIZED,
                function_associations=[
                    cf.FunctionAssociation(
                        function=spa_rewrite,
                        event_type=cf.FunctionEventType.VIEWER_REQUEST,
                    )
                ],
            ),
            default_root_object="index.html",
            http_version=cf.HttpVersion.HTTP2_AND_3,
            price_class=cf.PriceClass.PRICE_CLASS_100,
            additional_behaviors=additional_behaviors,
        )

        # ── Deploy frontend assets to S3 ─────────────────────────────────────
        s3deploy.BucketDeployment(
            self, "Deploy",
            sources=[s3deploy.Source.asset(FRONTEND_DIST)],
            destination_bucket=bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            cache_control=[s3deploy.CacheControl.no_cache()],
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        self.cloudfront_url = f"https://{distribution.distribution_domain_name}"
        cdk.CfnOutput(self, "CloudFrontUrl", value=self.cloudfront_url)
        cdk.CfnOutput(self, "BucketName",    value=bucket.bucket_name)
        cdk.CfnOutput(self, "DistributionId", value=distribution.distribution_id)
