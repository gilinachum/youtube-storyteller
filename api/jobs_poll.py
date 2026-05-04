"""Jobs poll handler — lightweight endpoint for frontend to check job status.

GET /jobs/poll?session_id=X

Returns: { has_pending: bool, has_unconsumed: bool }

- has_pending:    true if any jobs are status="started" and consumed=false
- has_unconsumed: true if any jobs are status in ("completed","failed") and consumed=false

The frontend uses this to decide whether to start/continue polling (has_pending)
and whether to notify the agent about finished work (has_unconsumed).

This Lambda is intentionally dumb — it only reads DynamoDB.
It never calls external services and knows nothing about job types.
"""
import json
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr

try:
    from _auth_context import caller_email
except ImportError:
    from api._auth_context import caller_email

JOBS_TABLE = os.environ.get("JOBS_TABLE", "storyteller-dev-jobs")

dynamodb = boto3.resource("dynamodb")


def handler(event, context):
    try:
        email = caller_email(event)
        if not email:
            return _response(401, {"error": "unauthenticated"})

        params = event.get("queryStringParameters") or {}
        session_id = params.get("session_id", "").strip()
        if not session_id:
            return _response(400, {"error": "session_id is required"})

        table = dynamodb.Table(JOBS_TABLE)

        # Query all jobs for this session
        result = table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            FilterExpression=Attr("consumed").eq(False),
        )
        jobs = result.get("Items", [])

        has_pending = any(j.get("status") == "started" for j in jobs)
        has_unconsumed = any(j.get("status") in ("completed", "failed") for j in jobs)

        return _response(200, {
            "has_pending": has_pending,
            "has_unconsumed": has_unconsumed,
        })

    except Exception as e:
        return _response(500, {"error": str(e)})


def _response(code, body):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
