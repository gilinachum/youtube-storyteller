"""Transcription Handler — checks AWS Transcribe status and completes jobs.

Invoked asynchronously by Job Resolver for each job with job_type="transcription".

Flow:
  1. GetTranscriptionJob(transcribe_job_name)
  2. If IN_PROGRESS / QUEUED → exit (resolver retries next minute)
  3. If COMPLETED:
       - Download transcript JSON from result URI
       - Save .txt to S3: uploads/{email}/{session_id}/{file_id}-transcript.txt
       - Record .txt in sessions table (files list)
       - Conditional update job: status="started" → "completed" (idempotent)
       - Delete Transcribe job (cleanup)
  4. If FAILED:
       - Conditional update job: status="started" → "failed"
       - Delete Transcribe job

The conditional update (ConditionExpression: status = "started") prevents duplicate
processing when two resolver ticks overlap and both invoke this handler.
"""
import json
import logging
import os
import uuid
import urllib.request
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

JOBS_TABLE = os.environ.get("JOBS_TABLE", "storyteller-jobs")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")

dynamodb = boto3.resource("dynamodb")
transcribe_client = boto3.client("transcribe")
s3 = boto3.client("s3")


def handler(event, context):
    """Handle a single transcription job."""
    job_id = event.get("job_id", "")
    session_id = event.get("session_id", "")
    email = event.get("email", "")
    metadata = event.get("metadata", {})

    transcribe_job_name = metadata.get("transcribe_job_name", "")
    if not transcribe_job_name:
        logger.error("Missing transcribe_job_name in metadata for job_id=%s", job_id)
        _fail_job(job_id, session_id, "Missing transcribe_job_name in metadata")
        return

    logger.info("Checking transcription job %s for job_id=%s", transcribe_job_name, job_id)

    try:
        resp = transcribe_client.get_transcription_job(TranscriptionJobName=transcribe_job_name)
        tj = resp["TranscriptionJob"]
        status = tj["TranscriptionJobStatus"]
    except transcribe_client.exceptions.BadRequestException:
        # Transcribe job doesn't exist — it was already cleaned up
        logger.warning("Transcribe job %s not found, likely already processed", transcribe_job_name)
        return
    except Exception as e:
        logger.error("Failed to get transcription job %s: %s", transcribe_job_name, e)
        return  # Retry next minute

    logger.info("Transcription job %s status: %s", transcribe_job_name, status)

    if status in ("IN_PROGRESS", "QUEUED"):
        # Not done yet — resolver will retry next minute
        return

    if status == "COMPLETED":
        _handle_completed(job_id, session_id, email, metadata, tj)
    elif status == "FAILED":
        reason = tj.get("FailureReason", "Transcription failed")
        logger.error("Transcription job %s FAILED: %s", transcribe_job_name, reason)
        _fail_job(job_id, session_id, reason)
        _cleanup_transcribe_job(transcribe_job_name)
    else:
        logger.warning("Unexpected transcription status %s for job %s", status, transcribe_job_name)


def _handle_completed(job_id: str, session_id: str, email: str, metadata: dict, tj: dict):
    """Download transcript, save to S3, update DDB."""
    transcribe_job_name = metadata.get("transcribe_job_name", "")
    original_filename = metadata.get("filename", "audio")

    # Download transcript JSON
    transcript_uri = tj["Transcript"]["TranscriptFileUri"]
    try:
        with urllib.request.urlopen(transcript_uri) as response:
            transcript_data = json.loads(response.read().decode("utf-8"))
        transcript_text = transcript_data["results"]["transcripts"][0]["transcript"]
    except Exception as e:
        logger.error("Failed to download transcript for job %s: %s", transcribe_job_name, e)
        return  # Retry next minute (idempotent — S3 write hasn't happened yet)

    # Detect language from Transcribe result
    identified_language = tj.get("LanguageCode", "")
    if not identified_language and tj.get("IdentifiedLanguageScore") is not None:
        identified_language = tj.get("LanguageCode", "unknown")

    # Save .txt to S3
    file_id = str(uuid.uuid4())[:8]
    base_name = original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
    txt_filename = f"{base_name}-transcript.txt"
    txt_key = f"uploads/{email}/{session_id}/{file_id}-{txt_filename}"

    try:
        s3.put_object(
            Bucket=UPLOAD_BUCKET,
            Key=txt_key,
            Body=transcript_text.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        logger.info("Saved transcript to s3://%s/%s", UPLOAD_BUCKET, txt_key)
    except Exception as e:
        logger.error("Failed to save transcript to S3: %s", e)
        return  # Retry next minute

    # Record .txt as session file in sessions table
    now = datetime.now(timezone.utc).isoformat()
    file_record = {
        "file_id": file_id,
        "filename": txt_filename,
        "s3_key": txt_key,
        "content_type": "text/plain",
        "uploaded_at": now,
        "source": "transcription",
    }
    try:
        sessions_table = dynamodb.Table(SESSIONS_TABLE)
        sessions_table.update_item(
            Key={"email": email, "session_id": session_id},
            UpdateExpression="SET files = list_append(if_not_exists(files, :empty), :new_file), updated_at = :now",
            ExpressionAttributeValues={
                ":new_file": [file_record],
                ":empty": [],
                ":now": now,
            },
        )
    except Exception as e:
        logger.warning("Failed to record session file for job_id=%s: %s", job_id, e)
        # Non-fatal — continue to mark job complete

    # Conditional update: started → completed (prevents duplicate processing)
    text_preview = transcript_text[:500] if transcript_text else ""
    result = {
        "s3_key": txt_key,
        "filename": txt_filename,
        "text_preview": text_preview,
        "language": identified_language,
    }
    try:
        jobs_table = dynamodb.Table(JOBS_TABLE)
        jobs_table.update_item(
            Key={"session_id": session_id, "job_id": job_id},
            UpdateExpression="SET #s = :completed, #r = :result, updated_at = :now",
            ConditionExpression=Attr("status").eq("started"),
            ExpressionAttributeNames={"#s": "status", "#r": "result"},
            ExpressionAttributeValues={
                ":completed": "completed",
                ":result": result,
                ":now": now,
            },
        )
        logger.info("Job %s marked completed", job_id)
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.info("Job %s already updated by another handler invocation (idempotent)", job_id)
    except Exception as e:
        logger.error("Failed to update job %s to completed: %s", job_id, e)
        return

    _cleanup_transcribe_job(transcribe_job_name)


def _fail_job(job_id: str, session_id: str, error_msg: str):
    """Conditionally mark job as failed."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        jobs_table = dynamodb.Table(JOBS_TABLE)
        jobs_table.update_item(
            Key={"session_id": session_id, "job_id": job_id},
            UpdateExpression="SET #s = :failed, #e = :error, updated_at = :now",
            ConditionExpression=Attr("status").eq("started"),
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={
                ":failed": "failed",
                ":error": error_msg,
                ":now": now,
            },
        )
        logger.info("Job %s marked failed: %s", job_id, error_msg)
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.info("Job %s conditional check failed (already updated)", job_id)
    except Exception as e:
        logger.error("Failed to mark job %s as failed: %s", job_id, e)


def _cleanup_transcribe_job(transcribe_job_name: str):
    """Delete the Transcribe job (best-effort cleanup)."""
    try:
        transcribe_client.delete_transcription_job(TranscriptionJobName=transcribe_job_name)
        logger.info("Deleted Transcribe job %s", transcribe_job_name)
    except Exception as e:
        logger.warning("Failed to delete Transcribe job %s: %s", transcribe_job_name, e)
