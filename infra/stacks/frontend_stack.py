"""Frontend stack — S3 + CloudFront for the React SPA + optional API origin.

The CloudFront distribution serves the SPA and proxies /api/* to API Gateway.
There's no edge auth by default — gate access by adding an auth provider
(Cognito, CloudFront signed cookies, Lambda@Edge, or similar).
"""
import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
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
                 api: apigw.RestApi | None = None,
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
        # Serves /index.html for any URI without a file extension, so client-side
        # routes (e.g. /auth/callback, /chat/xyz) still hit the SPA.
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

        # ── API prefix strip (viewer-request for /api/*) ────────────────────
        # CloudFront sends /api/foo → origin as /api/foo. API Gateway only knows
        # /foo. This strips /api so the origin sees /foo (stage path added by
        # RestApiOrigin automatically).
        api_rewrite = cf.Function(
            self, "ApiRewrite",
            function_name="storyteller-api-rewrite",
            code=cf.FunctionCode.from_inline("""
function handler(event) {
  var request = event.request;
  if (request.uri.indexOf('/api/') === 0) {
    request.uri = request.uri.substring(4);
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

        # /media/* — served directly from uploads bucket (no auth in public repo)
        if uploads_bucket_ref and media_oac:
            additional_behaviors["/media/*"] = cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    uploads_bucket_ref,
                    origin_access_control=media_oac,
                ),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_OPTIMIZED,
            )

        # /api/* — same-origin API via CloudFront (removes CORS)
        if api is not None:
            additional_behaviors["/api/*"] = cf.BehaviorOptions(
                origin=origins.RestApiOrigin(api),
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
