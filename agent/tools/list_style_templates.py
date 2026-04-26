"""List available style templates for thumbnail generation.

Templates are admin-managed PNG files in S3 with a JSON manifest.
"""

import json
import logging
import os

import boto3
from strands import tool

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "storytellerdata-uploadsbucket5e5e9b64-ysokbp7rrbw5")
TEMPLATES_PREFIX = "templates/thumbnails/"
TEMPLATES_MANIFEST = f"{TEMPLATES_PREFIX}templates.json"


@tool
def list_style_templates() -> str:
    """List available thumbnail style templates.

    Returns a JSON array of style templates with their descriptions
    and style notes. Each template has an ID, name, description,
    and an S3 key for the template image.

    Returns:
        JSON array of available style templates.
    """
    try:
        response = _s3.get_object(Bucket=UPLOAD_BUCKET, Key=TEMPLATES_MANIFEST)
        templates = json.loads(response["Body"].read().decode("utf-8"))
        # Add full S3 keys
        for t in templates:
            t["s3_key"] = f"{TEMPLATES_PREFIX}{t['id']}.png"
        return json.dumps(templates, ensure_ascii=False)
    except _s3.exceptions.NoSuchKey:
        return json.dumps([], ensure_ascii=False)
    except Exception as e:
        logger.warning("Failed to load style templates: %s", e)
        return json.dumps([], ensure_ascii=False)
