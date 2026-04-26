"""Save a user-uploaded image as a profile photo for thumbnail use.

Copies an uploaded file from the session uploads path to the user's
permanent profile photos folder, and updates the photos.json manifest.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from strands import tool

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "storytellerdata-uploadsbucket5e5e9b64-ysokbp7rrbw5")

# Image content types we accept as profile photos
VALID_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _photos_manifest_key(email: str) -> str:
    return f"profile/{email}/photos.json"


def _load_photos_manifest(email: str) -> list:
    try:
        response = _s3.get_object(
            Bucket=UPLOAD_BUCKET,
            Key=_photos_manifest_key(email),
        )
        return json.loads(response["Body"].read().decode("utf-8"))
    except _s3.exceptions.NoSuchKey:
        return []
    except Exception as e:
        logger.warning("Failed to load photos manifest for %s: %s", email, e)
        return []


def _save_photos_manifest(email: str, photos: list) -> None:
    _s3.put_object(
        Bucket=UPLOAD_BUCKET,
        Key=_photos_manifest_key(email),
        Body=json.dumps(photos, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def make_save_user_photo_tool(email: str):
    """Create a session-bound save_user_photo tool."""

    @tool
    def save_user_photo(
        s3_key: str,
        filename: str,
        description: str = "",
    ) -> str:
        """Save an uploaded image as a user profile photo for thumbnail use.

        Call this ONLY when the user explicitly indicates an uploaded image is their
        profile photo (e.g., "this is me", "save as my photo", "use this for thumbnails").
        Do NOT call this for content images, reference material, or documents.

        Args:
            s3_key: The S3 key of the uploaded file (from file_refs).
            filename: Original filename.
            description: Brief English description of the photo (what the person looks like,
                        expression, setting). The agent should describe what it sees.

        Returns:
            JSON with the saved photo metadata.
        """
        # Verify the source exists and is an image
        try:
            head = _s3.head_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
            content_type = head.get("ContentType", "")
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Cannot access uploaded file: {e}",
            }, ensure_ascii=False)

        if content_type and content_type not in VALID_IMAGE_TYPES:
            return json.dumps({
                "success": False,
                "error": f"File is not an image ({content_type}). Only JPEG, PNG, WebP, GIF are accepted.",
            }, ensure_ascii=False)

        # Generate profile photo path
        file_id = str(uuid.uuid4())[:8]
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
        profile_key = f"profile/{email}/photos/{file_id}.{ext}"

        # Copy to profile location
        try:
            _s3.copy_object(
                Bucket=UPLOAD_BUCKET,
                CopySource={"Bucket": UPLOAD_BUCKET, "Key": s3_key},
                Key=profile_key,
                ContentType=content_type or "image/jpeg",
            )
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to save profile photo: {e}",
            }, ensure_ascii=False)

        # Update manifest
        photos = _load_photos_manifest(email)
        now = datetime.now(timezone.utc).isoformat()
        photo_entry = {
            "file_id": file_id,
            "filename": filename,
            "s3_key": profile_key,
            "description": description,
            "uploaded_at": now,
        }
        photos.append(photo_entry)
        _save_photos_manifest(email, photos)

        return json.dumps({
            "success": True,
            "photo": photo_entry,
            "total_photos": len(photos),
            "message": f"Photo saved as profile photo ({len(photos)} total)",
        }, ensure_ascii=False)

    return save_user_photo
