"""Thumbnail proxy — generates fresh presigned URLs for thumbnail images.

GET /thumbnails?key=thumbnails/email/session/file.png
Returns 302 redirect to a fresh presigned S3 URL.
"""
import json
import os
import urllib.parse

import boto3

UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
s3 = boto3.client("s3")


def handler(event, context):
    try:
        params = event.get("queryStringParameters") or {}
        key = params.get("key", "")

        if not key:
            return _response(400, {"error": "key parameter required"})

        # Security: only allow thumbnail and profile paths
        if not key.startswith("thumbnails/") and not key.startswith("profile/"):
            return _response(403, {"error": "Access denied"})

        # Generate fresh presigned URL (1 hour)
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": UPLOAD_BUCKET, "Key": key},
            ExpiresIn=3600,
        )

        return {
            "statusCode": 302,
            "headers": {
                "Location": url,
                "Cache-Control": "private, max-age=3500",
                "Access-Control-Allow-Origin": "*",
            },
            "body": "",
        }

    except Exception as e:
        return _response(500, {"error": str(e)})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
