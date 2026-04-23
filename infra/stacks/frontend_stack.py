"""Frontend stack — S3 + CloudFront for the React SPA."""
import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cloudfront as cf,
    aws_cloudfront_origins as origins,
    RemovalPolicy,
)
from constructs import Construct

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")


class FrontendStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── S3 bucket (private — served via CloudFront only) ─────────────────
        bucket = s3.Bucket(
            self, "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # ── CloudFront OAC (Origin Access Control) ───────────────────────────
        oac = cf.S3OriginAccessControl(
            self, "OAC",
            description="StoryTeller frontend OAC",
        )

        # ── SPA path rewrite function (viewer-request) ───────────────────────
        spa_rewrite = cf.Function(
            self, "SpaRewrite",
            function_name="storyteller-spa-rewrite",
            code=cf.FunctionCode.from_inline("""
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  // If the URI has no extension (not a static asset), serve index.html
  if (!uri.match(/\\.[a-zA-Z0-9]{2,6}$/)) {
    request.uri = '/index.html';
  }
  return request;
}
"""),
            runtime=cf.FunctionRuntime.JS_2_0,
        )

        # ── CloudFront distribution ──────────────────────────────────────────
        distribution = cf.Distribution(
            self, "Distribution",
            comment="StoryTeller frontend",
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    bucket,
                    origin_access_control=oac,
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
            price_class=cf.PriceClass.PRICE_CLASS_100,  # US/Europe only
        )

        # ── Deploy frontend assets to S3 ─────────────────────────────────────
        s3deploy.BucketDeployment(
            self, "Deploy",
            sources=[s3deploy.Source.asset(FRONTEND_DIST)],
            destination_bucket=bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            cache_control=[
                # HTML — no cache (so new deployments take effect immediately)
                s3deploy.CacheControl.no_cache(),
            ],
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        self.cloudfront_url = f"https://{distribution.distribution_domain_name}"
        cdk.CfnOutput(self, "CloudFrontUrl", value=self.cloudfront_url)
        cdk.CfnOutput(self, "BucketName", value=bucket.bucket_name)
        cdk.CfnOutput(self, "DistributionId", value=distribution.distribution_id)
