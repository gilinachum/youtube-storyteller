"""Sessions handler — list, retrieve, share conversation sessions + file downloads."""
import json
import os
import boto3
from boto3.dynamodb.conditions import Key

try:
    from _auth_context import caller_email
except ImportError:
    from api._auth_context import caller_email


SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
MESSAGES_TABLE = os.environ.get("MESSAGES_TABLE", "storyteller-messages")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
s3 = boto3.client("s3", region_name="us-east-1")


def handler(event, context):
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "GET")
        path_params = event.get("pathParameters") or {}

        email = caller_email(event)
        if not email:
            return _response(401, {"error": "unauthenticated"})

        session_id = path_params.get("id")

        # DELETE /sessions/{id} — delete a session
        if method == "DELETE" and session_id and not path.endswith("/share") and "/files/" not in path:
            return delete_session(email, session_id)

        # POST /sessions/{id}/share — share a session
        if method == "POST" and session_id and path.endswith("/share"):
            return share_session(event, email, session_id)

        # GET /sessions/{id}/files/{file_id} — download a file
        if method == "GET" and "files" in path:
            file_id = path.split("/files/")[-1] if "/files/" in path else None
            if file_id and session_id:
                return download_file(session_id, file_id, email)

        if session_id:
            return get_session(session_id, email)
        else:
            return list_sessions(email)

    except Exception as e:
        import traceback
        return _response(500, {"error": str(e), "trace": traceback.format_exc()})


def list_sessions(email: str):
    table = dynamodb.Table(SESSIONS_TABLE)
    # Get own sessions
    result = table.query(KeyConditionExpression=Key("email").eq(email))
    sessions = result.get("Items", [])

    # Also get sessions shared with this user (scan shared_with)
    # For efficiency, we use a GSI in production. For now, check each session.
    # Shared sessions are stored with a special marker
    shared_result = table.scan(
        FilterExpression="contains(shared_with, :email)",
        ExpressionAttributeValues={":email": email},
    )
    shared_sessions = shared_result.get("Items", [])
    for s in shared_sessions:
        s["_shared"] = True
        s["_shared_by"] = s.get("email", "")

    all_sessions = sessions + shared_sessions
    all_sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)

    # Clean up for response
    for s in all_sessions:
        s.pop("files", None)  # Don't send full file list in session list

    return _response(200, {"sessions": all_sessions})


def get_session(session_id: str, email: str = ""):
    msgs_table = dynamodb.Table(MESSAGES_TABLE)
    result = msgs_table.query(KeyConditionExpression=Key("session_id").eq(session_id))
    messages = result.get("Items", [])
    messages.sort(key=lambda m: m.get("timestamp", ""))

    # Get session metadata (including files)
    sess_table = dynamodb.Table(SESSIONS_TABLE)
    # Try to find the session — could be under this email or shared
    session_meta = None
    if email:
        resp = sess_table.get_item(Key={"email": email, "session_id": session_id})
        session_meta = resp.get("Item")

    # If not found under this email, scan for it (shared session)
    if not session_meta:
        scan = sess_table.scan(
            FilterExpression="session_id = :sid",
            ExpressionAttributeValues={":sid": session_id},
            Limit=5,
        )
        items = scan.get("Items", [])
        if items:
            session_meta = items[0]

    files = session_meta.get("files", []) if session_meta else []
    shared_with = session_meta.get("shared_with", []) if session_meta else []

    return _response(200, {
        "session_id": session_id,
        "messages": messages,
        "files": files,
        "shared_with": shared_with,
    })


def share_session(event, owner_email: str, session_id: str):
    """Share a session with another user by email."""
    body = json.loads(event.get("body") or "{}")
    share_with_email = body.get("share_with", "").strip().lower()

    if not share_with_email:
        return _response(400, {"error": "share_with is required"})

    if owner_email == share_with_email:
        return _response(400, {"error": "Cannot share with yourself"})

    table = dynamodb.Table(SESSIONS_TABLE)

    # Add to shared_with list
    try:
        table.update_item(
            Key={"email": owner_email, "session_id": session_id},
            UpdateExpression="SET shared_with = list_append(if_not_exists(shared_with, :empty), :new_share)",
            ConditionExpression="NOT contains(if_not_exists(shared_with, :empty), :share_email)",
            ExpressionAttributeValues={
                ":new_share": [share_with_email],
                ":empty": [],
                ":share_email": share_with_email,
            },
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return _response(200, {"message": "Already shared", "shared_with": share_with_email})
    except Exception:
        # Fallback — just add it
        table.update_item(
            Key={"email": owner_email, "session_id": session_id},
            UpdateExpression="SET shared_with = list_append(if_not_exists(shared_with, :empty), :new_share)",
            ExpressionAttributeValues={
                ":new_share": [share_with_email],
                ":empty": [],
            },
        )

    return _response(200, {"message": "Session shared", "shared_with": share_with_email})


def delete_session(email: str, session_id: str):
    """Delete a session and all its messages."""
    sess_table = dynamodb.Table(SESSIONS_TABLE)
    msgs_table = dynamodb.Table(MESSAGES_TABLE)

    # Verify session belongs to this user
    resp = sess_table.get_item(Key={"email": email, "session_id": session_id})
    if not resp.get("Item"):
        return _response(404, {"error": "Session not found"})

    # Delete all messages for this session
    result = msgs_table.query(
        KeyConditionExpression=Key("session_id").eq(session_id),
        ProjectionExpression="session_id, #ts",
        ExpressionAttributeNames={"#ts": "timestamp"},
    )
    with msgs_table.batch_writer() as batch:
        for item in result.get("Items", []):
            batch.delete_item(Key={"session_id": item["session_id"], "timestamp": item["timestamp"]})

    # Delete the session itself
    sess_table.delete_item(Key={"email": email, "session_id": session_id})

    return _response(200, {"message": "Session deleted", "session_id": session_id})


def download_file(session_id: str, file_id: str, email: str):
    """Generate a presigned download URL for a file."""
    # Find the session to get the file's S3 key
    sess_table = dynamodb.Table(SESSIONS_TABLE)

    # Search for the session
    session_meta = None
    if email:
        resp = sess_table.get_item(Key={"email": email, "session_id": session_id})
        session_meta = resp.get("Item")

    if not session_meta:
        scan = sess_table.scan(
            FilterExpression="session_id = :sid",
            ExpressionAttributeValues={":sid": session_id},
            Limit=5,
        )
        items = scan.get("Items", [])
        if items:
            session_meta = items[0]

    if not session_meta:
        return _response(404, {"error": "Session not found"})

    files = session_meta.get("files", [])
    target_file = next((f for f in files if f.get("file_id") == file_id), None)
    if not target_file:
        return _response(404, {"error": "File not found"})

    # Generate presigned download URL
    download_url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": UPLOAD_BUCKET,
            "Key": target_file["s3_key"],
            "ResponseContentDisposition": f'attachment; filename="{target_file["filename"]}"',
        },
        ExpiresIn=604800,  # 7 days (S3 max)
    )

    return _response(200, {"download_url": download_url, "filename": target_file["filename"]})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }
