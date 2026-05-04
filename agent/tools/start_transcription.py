"""Start a transcription job for an uploaded audio or video file.

Writes a job record to DynamoDB and starts an AWS Transcribe job.
The Job Resolver picks it up every 60s and dispatches the Transcription Handler.
"""
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from strands import tool

logger = logging.getLogger(__name__)

JOBS_TABLE = os.environ.get("JOBS_TABLE", "storyteller-jobs")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
REGION = os.environ.get("AWS_REGION", "us-west-2")

# Estimate heuristic: ~1.5 MB/min of audio, Transcribe ~5x real-time
AUDIO_MB_PER_MINUTE = 1.5
TRANSCRIBE_SPEED_FACTOR = 5


def _estimate_seconds(s3_client, s3_key: str) -> int:
    """Estimate transcription completion time in seconds based on file size.

    Floor: 30s. Ceiling: 1200s (20 min). Fallback on error: 180s.
    """
    try:
        head = s3_client.head_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
        size_mb = head["ContentLength"] / (1024 * 1024)
        audio_minutes = size_mb / AUDIO_MB_PER_MINUTE
        transcription_seconds = int((audio_minutes / TRANSCRIBE_SPEED_FACTOR) * 60)
        return max(30, min(1200, transcription_seconds))
    except Exception as e:
        logger.warning("Could not estimate file duration for %s: %s", s3_key, e)
        return 180  # safe default


def make_start_transcription_tool(email: str, session_id: str):
    """Create a session-bound start_transcription tool."""

    # Create clients at factory time so they can be injected in tests
    _s3 = boto3.client("s3", region_name=REGION)
    _transcribe = boto3.client("transcribe", region_name=REGION)
    _dynamodb = boto3.resource("dynamodb", region_name=REGION)

    @tool
    def start_transcription(s3_key: str, filename: str, file_id: str = "") -> dict:
        """Start an AWS Transcribe job for an uploaded audio or video file.

        Call this when the user wants to transcribe an audio or video file they
        uploaded. Transcription runs asynchronously — the agent will be notified
        when it completes (usually 1–10 minutes depending on file size).

        Do NOT call this for image or document files — only audio/video.

        Args:
            s3_key: The S3 key of the uploaded file (from file_refs).
            filename: The original filename (used to name the output transcript).
            file_id: Optional file ID (informational, stored in job metadata).

        Returns:
            dict with job_id and estimated_seconds.
        """
        estimated_seconds = _estimate_seconds(_s3, s3_key)

        job_id = str(uuid.uuid4())
        transcribe_job_name = f"storyteller-{job_id[:8]}"
        media_uri = f"s3://{UPLOAD_BUCKET}/{s3_key}"

        # Start Transcribe job — IdentifyLanguage, no MediaFormat (auto-detect)
        _transcribe.start_transcription_job(
            TranscriptionJobName=transcribe_job_name,
            Media={"MediaFileUri": media_uri},
            IdentifyLanguage=True,
            LanguageOptions=["he-IL", "en-US"],
        )

        # Write job record to DDB
        now = datetime.now(timezone.utc)
        ttl = int((now + timedelta(days=365)).timestamp())

        table = _dynamodb.Table(JOBS_TABLE)
        table.put_item(Item={
            "session_id": session_id,
            "job_id": job_id,
            "email": email,
            "job_type": "transcription",
            "status": "started",
            "consumed": False,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "metadata": {
                "transcribe_job_name": transcribe_job_name,
                "s3_key": s3_key,
                "file_id": file_id,
                "filename": filename,
            },
            "ttl": ttl,
        })

        logger.info("Started transcription job %s for session %s (est. %ds)",
                    job_id, session_id, estimated_seconds)

        return {
            "job_id": job_id,
            "estimated_seconds": estimated_seconds,
            "message": f"Transcription started. Estimated ~{estimated_seconds // 60} minutes.",
        }

    return start_transcription
