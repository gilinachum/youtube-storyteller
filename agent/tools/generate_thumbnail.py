"""Generate thumbnail images using Gemini Flash Preview.

Calls the Gemini API with text prompts (and optional reference images)
to generate YouTube thumbnail images at 1280×720.
"""

import base64
import json
import logging
import os
import uuid
from typing import Optional

import boto3
from strands import tool

logger = logging.getLogger(__name__)

# Lazily initialized Gemini client
_gemini_client = None
_s3 = boto3.client("s3")
_secrets = boto3.client("secretsmanager")

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "storytellerdata-uploadsbucket5e5e9b64-ysokbp7rrbw5")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
GEMINI_MODEL = "gemini-3.1-flash-image-preview"

_dynamodb = boto3.resource("dynamodb")


def _get_gemini_client():
    """Get or create the Gemini client (lazy init)."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        api_key = _secrets.get_secret_value(SecretId="gcp/gemini-api-key")["SecretString"]
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _upload_to_s3(image_data: bytes, email: str, session_id: str, filename: str) -> str:
    """Upload generated image to S3 and return the S3 key."""
    key = f"media/thumbnails/{email}/{session_id}/{filename}"
    _s3.put_object(
        Bucket=UPLOAD_BUCKET,
        Key=key,
        Body=image_data,
        ContentType="image/png",
    )
    return key


def _register_file(email: str, session_id: str, file_id: str, s3_key: str) -> None:
    """Register a generated file in the session's files array for download_file."""
    from datetime import datetime, timezone
    try:
        table = _dynamodb.Table(SESSIONS_TABLE)
        now = datetime.now(timezone.utc).isoformat()
        table.update_item(
            Key={"email": email, "session_id": session_id},
            UpdateExpression="SET #f = list_append(if_not_exists(#f, :empty), :files), updated_at = :now",
            ExpressionAttributeNames={"#f": "files"},
            ExpressionAttributeValues={
                ":files": [{
                    "file_id": file_id,
                    "filename": file_id,
                    "s3_key": s3_key,
                    "content_type": "image/png",
                    "uploaded_at": now,
                }],
                ":empty": [],
                ":now": now,
            },
        )
    except Exception as e:
        logger.warning("Failed to register thumbnail file in session: %s", e)



def _load_reference_image(s3_key: str) -> Optional[dict]:
    """Load an image from S3 as a Gemini-compatible part."""
    try:
        response = _s3.get_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
        image_data = response["Body"].read()
        content_type = response.get("ContentType", "image/jpeg")
        return {
            "inline_data": {
                "mime_type": content_type,
                "data": base64.b64encode(image_data).decode("utf-8"),
            }
        }
    except Exception as e:
        logger.warning("Failed to load reference image %s: %s", s3_key, e)
        return None


def make_generate_thumbnail_tool(email: str, session_id: str = ""):
    """Create a session-bound generate_thumbnail tool with the user's email and session ID."""

    # Pre-bind session_id so the sub-agent model doesn't need to know it
    _bound_session_id = session_id

    @tool
    def generate_thumbnail(
        prompt: str,
        reference_image_keys: str = "",
        style_notes: str = "",
    ) -> str:
        """Generate a YouTube thumbnail image using Gemini.

        Args:
            prompt: Detailed English description of the thumbnail to generate.
                    Include: composition, colors, text overlay, style, mood.
                    Always specify "YouTube thumbnail, 1280x720".
            reference_image_keys: Comma-separated S3 keys of reference images
                                 (user photos, style templates, existing thumbnails).
            style_notes: Additional style guidance (e.g., from a style template).

        Returns:
            JSON with the generated thumbnail URL and metadata.
        """
        from google.genai import types

        client = _get_gemini_client()

        # Build the full prompt
        full_prompt = f"Generate a YouTube thumbnail image, exactly 1280x720 pixels, high quality.\n\n{prompt}"
        if style_notes:
            full_prompt += f"\n\nStyle guidance: {style_notes}"

        # Build content parts
        contents = []

        # Add reference images if provided
        if reference_image_keys:
            keys = [k.strip() for k in reference_image_keys.split(",") if k.strip()]
            for key in keys:
                ref = _load_reference_image(key)
                if ref:
                    from google.genai import types as gtypes
                    contents.append(gtypes.Part(
                        inline_data=gtypes.Blob(
                            mime_type=ref["inline_data"]["mime_type"],
                            data=base64.b64decode(ref["inline_data"]["data"]),
                        )
                    ))

        # Add the text prompt
        contents.append(full_prompt)

        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )

            # Extract image and text from response
            image_data = None
            text_response = ""
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    data = part.inline_data.data
                    if isinstance(data, str):
                        image_data = base64.b64decode(data)
                    else:
                        image_data = data
                elif part.text:
                    text_response += part.text

            if not image_data:
                return json.dumps({
                    "success": False,
                    "error": "No image generated by Gemini",
                    "text_response": text_response,
                }, ensure_ascii=False)

            # Save to S3 under email/session path
            file_id = f"thumb-{uuid.uuid4()}.png"  # flat id — safe for API GW path
            s3_key = _upload_to_s3(image_data, email, _bound_session_id or "default", file_id)

            # Register file in session so download_file can resolve it
            _register_file(email, _bound_session_id or "default", file_id, s3_key)

            return (
                f"IMAGE_MARKDOWN_START\n"
                f"![thumbnail](media://{file_id})\n"
                f"IMAGE_MARKDOWN_END\n\n"
                + json.dumps({
                    "success": True,
                    "file_id": file_id,
                    "s3_key": s3_key,
                    "filename": file_id,
                    "size_bytes": len(image_data),
                    "prompt_used": prompt[:500],
                    "text_response": text_response,
                }, ensure_ascii=False)
            )

        except Exception as e:
            logger.error("Gemini image generation failed: %s", e, exc_info=True)
            return json.dumps({
                "success": False,
                "error": str(e),
            }, ensure_ascii=False)

    return generate_thumbnail
