"""List jobs that completed or failed but haven't been consumed by the agent yet."""
import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key
from strands import tool

logger = logging.getLogger(__name__)

JOBS_TABLE = os.environ.get("JOBS_TABLE", "storyteller-jobs")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")


def make_list_pending_jobs_tool(email: str, session_id: str):
    """Create a session-bound list_pending_jobs tool."""

    @tool
    def list_pending_jobs() -> str:
        """List finished jobs (completed or failed) that haven't been processed yet.

        Call this after being notified that async jobs are ready (e.g., when the
        frontend says "יש עבודות שהסתיימו"). Returns all unconsumed completed or
        failed jobs for the current session.

        After processing each result, call mark_job_consumed(job_id) to prevent
        re-notification.

        Returns:
            JSON with a list of job objects including results and metadata.
        """
        try:
            table = dynamodb.Table(JOBS_TABLE)
            result = table.query(
                KeyConditionExpression=Key("session_id").eq(session_id),
            )
            all_jobs = result.get("Items", [])

            # Filter: unconsumed AND terminal status
            pending = [
                item for item in all_jobs
                if not item.get("consumed", False)
                and item.get("status") in ("completed", "failed")
            ]

            jobs = []
            for item in pending:
                job = {
                    "job_id": item["job_id"],
                    "job_type": item.get("job_type", ""),
                    "status": item["status"],
                    "result": item.get("result"),
                    "error": item.get("error"),
                    "metadata": item.get("metadata", {}),
                    "created_at": item.get("created_at", ""),
                }

                # Generate presigned download URL for completed transcription files
                result_data = item.get("result") or {}
                s3_key = result_data.get("s3_key", "") if isinstance(result_data, dict) else ""
                if s3_key and UPLOAD_BUCKET and item.get("status") == "completed":
                    try:
                        filename = s3_key.split("/")[-1]
                        download_url = s3.generate_presigned_url(
                            "get_object",
                            Params={
                                "Bucket": UPLOAD_BUCKET,
                                "Key": s3_key,
                                "ResponseContentDisposition": f'attachment; filename="{filename}"',
                            },
                            ExpiresIn=3600,
                        )
                        job["download_url"] = download_url
                    except Exception as e:
                        logger.warning("Failed to generate presigned URL for %s: %s", s3_key, e)

                jobs.append(job)

            return json.dumps({"jobs": jobs, "count": len(jobs)}, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error("Failed to list pending jobs: %s", e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    return list_pending_jobs
