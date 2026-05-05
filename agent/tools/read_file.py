"""Read a text file from the uploads S3 bucket."""
import json
import logging
import os

import boto3
from strands import tool

logger = logging.getLogger(__name__)

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")

s3 = boto3.client("s3")


def make_read_file_tool(session_id: str, email: str):
    """Create a session-bound read_file tool."""

    @tool
    def read_file(s3_key: str) -> str:
        """Read the contents of a text file from session storage.

        Use this to read transcription results, notes, or any text file that was
        uploaded or generated for the current session.

        The s3_key is available from:
        - Job results (result.s3_key from list_pending_jobs)
        - File records (s3_key from the session's file list)

        Args:
            s3_key: The S3 key of the file to read (e.g., "uploads/user@email.com/session-id/file.txt")

        Returns:
            The full text content of the file, or an error message.
        """
        if not UPLOAD_BUCKET:
            return json.dumps({"error": "UPLOAD_BUCKET not configured"})

        # Security: only allow reading files from the current session
        expected_prefix = f"uploads/{email}/{session_id}/"
        if not s3_key.startswith(expected_prefix):
            return json.dumps({
                "error": f"Access denied: can only read files from current session",
                "hint": f"Expected prefix: {expected_prefix}",
            }, ensure_ascii=False)

        try:
            response = s3.get_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
            content_type = response.get("ContentType", "")

            # Only read text-like files (safety guard)
            body = response["Body"].read()

            # Try to decode as text
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                return json.dumps({
                    "error": "File is not a text file (binary content)",
                    "content_type": content_type,
                }, ensure_ascii=False)

            # Truncate very large files (>50KB) to prevent context overflow
            MAX_CHARS = 50_000
            truncated = len(text) > MAX_CHARS
            if truncated:
                text = text[:MAX_CHARS]

            return json.dumps({
                "content": text,
                "filename": s3_key.split("/")[-1],
                "size": len(body),
                "truncated": truncated,
            }, ensure_ascii=False)

        except s3.exceptions.NoSuchKey:
            return json.dumps({"error": f"File not found: {s3_key}"}, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to read file %s: %s", s3_key, e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    return read_file
