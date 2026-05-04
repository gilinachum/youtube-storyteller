from __future__ import annotations

"""Backup stack — AWS Backup for DynamoDB daily snapshots with 90-day retention."""
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_backup as backup,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_events as events,
)
from constructs import Construct


class BackupStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        prefix: str = "storyteller",
        table_arns: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── Backup vault ────────────────────────────────────────────────────
        vault = backup.BackupVault(
            self,
            "DynamoDbDailyVault",
            backup_vault_name=f"{prefix}-dynamodb-daily",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── IAM role for AWS Backup ─────────────────────────────────────────
        backup_role = iam.Role(
            self,
            "BackupRole",
            role_name=f"{prefix}-backup-role",
            assumed_by=iam.ServicePrincipal("backup.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSBackupServiceRolePolicyForBackup"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSBackupServiceRolePolicyForRestores"
                ),
            ],
        )

        # ── Backup plan: daily at 01:00 UTC, 90-day retention ──────────────
        plan = backup.BackupPlan(
            self,
            "DynamoDbDailyPlan",
            backup_plan_name=f"{prefix}-dynamodb-daily",
            backup_plan_rules=[
                backup.BackupPlanRule(
                    rule_name="daily-90d",
                    backup_vault=vault,
                    schedule_expression=events.Schedule.cron(
                        hour="1", minute="0"
                    ),
                    start_window=Duration.hours(1),
                    completion_window=Duration.hours(3),
                    delete_after=Duration.days(90),
                ),
            ],
        )

        # ── Add CDK-managed tables ──────────────────────────────────────────
        if table_arns:
            for i, arn in enumerate(table_arns):
                plan.add_selection(
                    f"Table{i}",
                    resources=[backup.BackupResource.from_arn(arn)],
                    role=backup_role,
                )
