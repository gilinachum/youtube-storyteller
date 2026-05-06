"""Data stack — DynamoDB tables + S3 uploads bucket."""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class DataStack(Stack):
    def __init__(self, scope: Construct, id: str, prefix: str = "storyteller", **kwargs):
        super().__init__(scope, id, **kwargs)

        # Table names are fixed (same in dev and prod — deployed to different regions)
        # ── Sessions table ──────────────────────────────────────────────────
        self.sessions_table = dynamodb.Table(
            self, "SessionsTable",
            table_name="storyteller-sessions",
            partition_key=dynamodb.Attribute(name="email", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=True),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── Messages table ──────────────────────────────────────────────────
        self.messages_table = dynamodb.Table(
            self, "MessagesTable",
            table_name="storyteller-messages",
            partition_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=True),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── Jobs table (long-running async jobs — transcription, analysis, etc.) ──
        self.jobs_table = dynamodb.Table(
            self, "JobsTable",
            table_name="storyteller-jobs",
            partition_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="job_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(point_in_time_recovery_enabled=True),
            removal_policy=RemovalPolicy.DESTROY,  # ephemeral — TTL'd rows, no prod data
        )
        # GSI: query all jobs by status (used by Job Resolver to find started jobs)
        self.jobs_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── Uploads bucket ──────────────────────────────────────────────────
        self.uploads_bucket = s3.Bucket(
            self, "UploadsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="expire-uploads",
                    enabled=True,
                    expiration=Duration.days(365),  # keep uploads/transcripts for 1 year
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST],
                    allowed_origins=["*"],  # tighten to CF domain in Phase 3
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
        )

        # ── Outputs ─────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "SessionsTableName", value=self.sessions_table.table_name)
        cdk.CfnOutput(self, "MessagesTableName", value=self.messages_table.table_name)
        cdk.CfnOutput(self, "JobsTableName", value=self.jobs_table.table_name)
        cdk.CfnOutput(self, "UploadsBucketName", value=self.uploads_bucket.bucket_name)
