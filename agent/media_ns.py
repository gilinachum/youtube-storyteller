"""User media namespace — maps email to an opaque UUID for S3 paths.

Uses HMAC-SHA256(email, salt) to generate a deterministic but unguessable
namespace. The salt is stored in Secrets Manager.

S3 paths: media/{user_ns}/thumbnails/..., media/{user_ns}/photos/...
CloudFront paths: /media/{user_ns}/thumbnails/..., /media/{user_ns}/photos/...
"""

import hashlib
import hmac
import logging
import os

import boto3

logger = logging.getLogger(__name__)

_salt: str | None = None
_secrets = boto3.client("secretsmanager", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

SALT_SECRET_ID = "storyteller/media-salt"


def _get_salt() -> str:
    """Load the media namespace salt from Secrets Manager (cached)."""
    global _salt
    if _salt is None:
        _salt = _secrets.get_secret_value(SecretId=SALT_SECRET_ID)["SecretString"]
    return _salt


def user_namespace(email: str) -> str:
    """Generate a deterministic opaque namespace for a user email.

    Returns a 16-char hex string derived from HMAC-SHA256(email, salt).
    Same email always produces the same namespace.
    """
    salt = _get_salt()
    mac = hmac.new(salt.encode(), email.lower().strip().encode(), hashlib.sha256)
    return mac.hexdigest()[:16]
