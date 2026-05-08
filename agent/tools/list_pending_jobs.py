"""List jobs that completed or failed but haven't been consumed by the agent yet."""
import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key
from strands import tool

logger = logging.getLogger(__name__)

JOBS_TABLE = os.environ.get("JOBS_TABLE", "storyteller-jobs")

dynamodb = boto3.resource("dynamodb")


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

                # For completed jobs with files, provide a file:// reference
                # (frontend resolves these on-demand via /api/sessions/{id}/files/{file_id})
                result_data = item.get("result") or {}
                s3_key = result_data.get("s3_key", "") if isinstance(result_data, dict) else ""
                if s3_key and item.get("status") == "completed":
                    import re
                    filename = s3_key.split("/")[-1]
                    display_name = filename
                    file_id = result_data.get("file_id", "")
                    if not file_id:
                        # Extract file_id from s3_key: {file_id}-{filename}
                        name_part = s3_key.split("/")[-1]
                        match = re.match(r'^([0-9a-f]{8})-(.+)$', name_part)
                        if match:
                            file_id = match.group(1)
                            display_name = match.group(2)
                        elif re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-', name_part):
                            file_id = name_part[:36]
                            display_name = name_part[37:]
                    else:
                        if filename.startswith(file_id):
                            display_name = filename[len(file_id)+1:]
                    job["file_id"] = file_id
                    job["filename"] = display_name
                    job["download_link"] = f"[📄 {display_name}](file://{file_id})"

                jobs.append(job)

            return json.dumps({"jobs": jobs, "count": len(jobs)}, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error("Failed to list pending jobs: %s", e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    return list_pending_jobs
