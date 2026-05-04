"""Mark a job as consumed after the agent has processed its result."""
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from strands import tool

logger = logging.getLogger(__name__)

JOBS_TABLE = os.environ.get("JOBS_TABLE", "storyteller-jobs")

dynamodb = boto3.resource("dynamodb")


def make_mark_job_consumed_tool(session_id: str, email: str = ""):
    """Create a session-bound mark_job_consumed tool."""

    @tool
    def mark_job_consumed(job_id: str) -> str:
        """Mark a job as consumed after processing its result.

        Call this immediately after reading and acting on a job's result from
        list_pending_jobs. Setting consumed=true prevents the frontend from
        re-notifying about this job.

        Args:
            job_id: The job ID to mark as consumed.

        Returns:
            JSON with success status.
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            table = dynamodb.Table(JOBS_TABLE)
            table.update_item(
                Key={"session_id": session_id, "job_id": job_id},
                UpdateExpression="SET consumed = :true, updated_at = :now",
                ExpressionAttributeValues={
                    ":true": True,
                    ":now": now,
                },
            )
            logger.info("Marked job %s as consumed (session=%s)", job_id, session_id)
            return json.dumps({"success": True, "job_id": job_id}, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to mark job %s consumed: %s", job_id, e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return mark_job_consumed
