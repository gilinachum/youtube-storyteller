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
        """Read the contents of a text file from session storage into your context.

        Use this to INGEST transcription results so you can reference them when
        planning videos. Call this once per file — the content stays in your
        conversation context for subsequent turns.

        Do NOT paste the full file content back to the user in chat — just
        summarize the key points. The file is already available for download
        in the session's file list.

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

            # Provide a file:// reference for on-demand download
            filename = s3_key.split("/")[-1]
            # Extract file_id from key pattern: uploads/{email}/{session}/{file_id}-{filename}
            # file_id is typically 8 hex chars (short ID)
            file_id = ""
            parts = s3_key.split("/")
            if len(parts) >= 4:
                name_part = parts[-1]
                # Match 8-hex-char prefix: "952d2ce2-filename.txt"
                import re
                match = re.match(r'^([0-9a-f]{8})-(.+)$', name_part)
                if match:
                    file_id = match.group(1)
                    filename = match.group(2)
                # Also handle full UUID prefix: "952d2ce2-1234-5678-abcd-ef0123456789-filename.txt"
                elif re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-', name_part):
                    file_id = name_part[:36]
                    filename = name_part[37:]

            return json.dumps({
                "content": text,
                "filename": filename,
                "size": len(body),
                "truncated": truncated,
                "file_id": file_id,
                "download_link": f"[\ud83d\udcc4 {filename}](file://{file_id})" if file_id else None,
            }, ensure_ascii=False)

        except s3.exceptions.NoSuchKey:
            return json.dumps({"error": f"File not found: {s3_key}"}, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to read file %s: %s", s3_key, e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    return read_file
