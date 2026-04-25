"""Transcribe handler — async pattern with start + poll.

POST /transcribe — upload audio, start Transcribe job, return job_name
GET /transcribe/{job_name} — poll for completion, return transcript
"""
import json
import os
import uuid
import time
import base64
import boto3
import urllib.request

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=REGION)
transcribe_client = boto3.client("transcribe", region_name=REGION)


def handler(event, context):
    method = event.get("httpMethod", "")
    path_params = event.get("pathParameters") or {}

    if method == "POST":
        return _start_transcription(event)
    elif method == "GET" and path_params.get("job_name"):
        return _poll_transcription(path_params["job_name"])
    else:
        return _response(400, {"error": "Invalid request"})


def _start_transcription(event):
    """Upload audio to S3 and start Transcribe job. Returns immediately."""
    try:
        body = json.loads(event.get("body") or "{}")
        email = body.get("email", "").strip().lower()
        session_id = body.get("session_id", "").strip()
        audio_data = body.get("audio", "")  # base64-encoded audio

        if not email or not session_id or not audio_data:
            return _response(400, {"error": "email, session_id, and audio are required"})

        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_data)

        # Upload to S3
        file_id = str(uuid.uuid4())[:8]
        s3_key = f"voice/{email}/{session_id}/{file_id}.webm"

        s3.put_object(
            Bucket=UPLOAD_BUCKET,
            Key=s3_key,
            Body=audio_bytes,
            ContentType="audio/webm",
        )

        # Start transcription job
        job_name = f"storyteller-{file_id}-{int(time.time())}"
        media_uri = f"s3://{UPLOAD_BUCKET}/{s3_key}"

        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": media_uri},
            IdentifyLanguage=True,
            LanguageOptions=["he-IL", "en-US"],
            MediaFormat="webm",
        )

        # Return immediately with job reference
        return _response(200, {
            "job_name": job_name,
            "status": "IN_PROGRESS",
            "s3_key": s3_key,
        })

    except Exception as e:
        return _response(500, {"error": str(e)})


def _poll_transcription(job_name):
    """Check transcription job status. Returns transcript when complete."""
    try:
        result = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        job = result["TranscriptionJob"]
        status = job["TranscriptionJobStatus"]

        if status == "COMPLETED":
            # Get transcript
            transcript_uri = job["Transcript"]["TranscriptFileUri"]
            with urllib.request.urlopen(transcript_uri) as resp:  # noqa: S310
                transcript_data = json.loads(resp.read().decode("utf-8"))

            text = transcript_data["results"]["transcripts"][0]["transcript"]
            lang_code = job.get("LanguageCode", "unknown")

            # Clean up
            try:
                s3_key = job.get("Media", {}).get("MediaFileUri", "").split(f"{UPLOAD_BUCKET}/", 1)[-1]
                if s3_key:
                    s3.delete_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
                transcribe_client.delete_transcription_job(TranscriptionJobName=job_name)
            except Exception:
                pass  # Best effort

            return _response(200, {
                "status": "COMPLETED",
                "text": text,
                "language": lang_code,
            })

        elif status == "FAILED":
            reason = job.get("FailureReason", "Unknown error")
            # Clean up failed job
            try:
                transcribe_client.delete_transcription_job(TranscriptionJobName=job_name)
            except Exception:
                pass
            return _response(200, {
                "status": "FAILED",
                "error": f"Transcription failed: {reason}",
            })

        else:
            # Still processing
            return _response(200, {
                "status": "IN_PROGRESS",
            })

    except transcribe_client.exceptions.BadRequestException:
        return _response(404, {"error": "Job not found"})
    except Exception as e:
        return _response(500, {"error": str(e)})


def _response(code, body):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }
