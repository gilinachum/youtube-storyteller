"""Transcribe handler — receive audio blob, transcribe with Amazon Transcribe."""
import json
import os
import uuid
import time
import base64
import boto3

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=REGION)
transcribe = boto3.client("transcribe", region_name=REGION)


def handler(event, context):
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

        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": media_uri},
            IdentifyLanguage=True,
            LanguageOptions=["he-IL", "en-US"],
            MediaFormat="webm",
        )

        # Poll for completion (Lambda has up to 29s)
        for _ in range(58):  # ~29 seconds max
            time.sleep(0.5)
            result = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            status = result["TranscriptionJob"]["TranscriptionJobStatus"]

            if status == "COMPLETED":
                # Get transcript from result URL
                transcript_uri = result["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                import urllib.request
                with urllib.request.urlopen(transcript_uri) as resp:
                    transcript_data = json.loads(resp.read().decode("utf-8"))

                text = transcript_data["results"]["transcripts"][0]["transcript"]
                language = result["TranscriptionJob"].get("IdentifiedLanguageScore", "")
                lang_code = result["TranscriptionJob"].get("LanguageCode", "unknown")

                # Clean up: delete S3 audio and transcription job
                try:
                    s3.delete_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
                    transcribe.delete_transcription_job(TranscriptionJobName=job_name)
                except Exception:
                    pass  # Best effort cleanup

                return _response(200, {
                    "text": text,
                    "language": lang_code,
                })

            elif status == "FAILED":
                reason = result["TranscriptionJob"].get("FailureReason", "Unknown error")
                return _response(500, {"error": f"Transcription failed: {reason}"})

        # Timeout — still processing
        return _response(504, {"error": "Transcription timed out. Try a shorter message."})

    except Exception as e:
        return _response(500, {"error": str(e)})


def _response(code, body):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }
