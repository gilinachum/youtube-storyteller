"""Job Resolver — central coordinator that runs every 60s via EventBridge.

Scans for all jobs with status="started" and asynchronously dispatches
a type-specific handler Lambda for each one.

This Lambda:
- Knows job types (for routing)
- Does NOT touch the consumed field
- Does NOT wait for handlers to complete (fire-and-forget)
- Is cheap: one GSI query + N async Lambda invocations
"""
import json
import os
import logging
import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

JOBS_TABLE = os.environ.get("JOBS_TABLE", "storyteller-dev-jobs")
TRANSCRIPTION_HANDLER_FN = os.environ.get("TRANSCRIPTION_HANDLER_FN", "storyteller-transcription-handler")

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

# Map job_type → handler Lambda function name
JOB_TYPE_HANDLERS = {
    "transcription": TRANSCRIPTION_HANDLER_FN,
    # Future: "video_analysis": os.environ.get("VIDEO_ANALYSIS_HANDLER_FN", ""),
}


def handler(event, context):
    """EventBridge trigger — scan for started jobs and dispatch handlers."""
    try:
        table = dynamodb.Table(JOBS_TABLE)

        # Query GSI for all jobs with status="started"
        result = table.query(
            IndexName="status-index",
            KeyConditionExpression=Key("status").eq("started"),
        )
        jobs = result.get("Items", [])

        if not jobs:
            logger.debug("No started jobs found")
            return {"dispatched": 0}

        logger.info("Found %d started job(s)", len(jobs))
        dispatched = 0

        for job in jobs:
            job_type = job.get("job_type", "")
            handler_fn = JOB_TYPE_HANDLERS.get(job_type)

            if not handler_fn:
                logger.warning("No handler registered for job_type=%s job_id=%s", job_type, job.get("job_id"))
                continue

            payload = {
                "job_id": job["job_id"],
                "session_id": job["session_id"],
                "email": job.get("email", ""),
                "job_type": job_type,
                "metadata": job.get("metadata", {}),
            }

            try:
                lambda_client.invoke(
                    FunctionName=handler_fn,
                    InvocationType="Event",  # fire-and-forget async
                    Payload=json.dumps(payload),
                )
                dispatched += 1
                logger.info("Dispatched handler for job_id=%s job_type=%s", job["job_id"], job_type)
            except Exception as e:
                logger.error("Failed to invoke handler for job_id=%s: %s", job["job_id"], e)

        return {"dispatched": dispatched, "total_started": len(jobs)}

    except Exception as e:
        logger.error("Job resolver error: %s", e)
        raise
