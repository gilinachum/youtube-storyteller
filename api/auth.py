"""Auth handler — validate email and return session token."""
import json
import uuid


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        email = body.get("email", "").strip().lower()

        if not email:
            return _response(400, {"error": "email is required"})

        token = str(uuid.uuid4())
        return _response(200, {"token": token, "email": email})

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
