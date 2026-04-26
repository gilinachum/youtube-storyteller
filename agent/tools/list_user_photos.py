"""List user profile photos for thumbnail generation.

Photos are stored per-user in S3 with a JSON metadata file.
"""

import json
import logging
import os

import boto3
from strands import tool

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "storytellerdata-uploadsbucket5e5e9b64-ysokbp7rrbw5")


def _photos_manifest_key(email: str) -> str:
    """Get the S3 key for a user's photos manifest."""
    return f"media/photos/{email}/photos.json"


def _get_user_photos(email: str) -> list:
    """Load user photos metadata from S3."""
    try:
        response = _s3.get_object(
            Bucket=UPLOAD_BUCKET,
            Key=_photos_manifest_key(email),
        )
        return json.loads(response["Body"].read().decode("utf-8"))
    except _s3.exceptions.NoSuchKey:
        return []
    except Exception as e:
        logger.warning("Failed to load photos for %s: %s", email, e)
        return []


def _save_user_photos(email: str, photos: list) -> None:
    """Save user photos metadata to S3."""
    _s3.put_object(
        Bucket=UPLOAD_BUCKET,
        Key=_photos_manifest_key(email),
        Body=json.dumps(photos, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def make_list_user_photos_tool(email: str):
    """Create a session-bound list_user_photos tool with the user's email."""

    @tool
    def list_user_photos() -> str:
        """List the user's uploaded profile photos for thumbnail use.

        Returns a JSON array of photo metadata including descriptions
        and emotional expressions detected in each photo.

        Returns:
            JSON array of user's profile photos with metadata.
        """
        photos = _get_user_photos(email)
        if not photos:
            return json.dumps({
                "photos": [],
                "message": "No profile photos uploaded yet. Ask the user to upload photos for personalized thumbnails.",
            }, ensure_ascii=False)

        return json.dumps({
            "photos": photos,
            "count": len(photos),
        }, ensure_ascii=False)

    return list_user_photos
