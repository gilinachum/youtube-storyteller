"""Sessions handler — list, retrieve, share conversation sessions + file downloads."""
import json
import os
import logging
import boto3
from botocore.config import Config
from boto3.dynamodb.conditions import Key

try:
    from _auth_context import caller_email
except ImportError:
    from api._auth_context import caller_email


logger = logging.getLogger(__name__)

SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
MESSAGES_TABLE = os.environ.get("MESSAGES_TABLE", "storyteller-messages")
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
AGENTCORE_MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID", "")

dynamodb = boto3.resource("dynamodb")
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))


def handler(event, context):
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "GET")
        path_params = event.get("pathParameters") or {}

        email = caller_email(event)
        if not email:
            return _response(401, {"error": "unauthenticated"})

        session_id = path_params.get("id")

        # DELETE /sessions/{id}/share/{email} — unshare a collaborator
        if method == "DELETE" and session_id and "/share/" in path:
            target_email = path.split("/share/")[-1]
            return unshare_session(email, session_id, target_email)

        # DELETE /sessions/{id} — delete a session
        if method == "DELETE" and session_id and "/files/" not in path:
            return delete_session(email, session_id)

        # PATCH /sessions/{id}/visibility — toggle visibility
        if method == "PATCH" and session_id and path.endswith("/visibility"):
            return set_visibility(event, email, session_id)

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


def _email_to_actor_id(email: str) -> str:
    """Convert email to valid AgentCore actorId."""
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")


def _extract_display_text(message: dict) -> str:
    """Extract display text from a Converse API message content block list."""
    content = message.get("content", [])
    parts = []
    for block in content:
        if isinstance(block, dict):
            if "text" in block:
                parts.append(block["text"])
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts)


def _get_messages_from_memory(session_id: str, email: str):
    """Try to read messages from AgentCore Memory via boto3. Returns None if unavailable."""
    if not AGENTCORE_MEMORY_ID or not email:
        return None

    try:
        region = os.environ.get("AWS_REGION", "us-west-2")
        client = boto3.client("bedrock-agentcore", region_name=region)

        actor_id = _email_to_actor_id(email)
        response = client.list_events(
            memoryId=AGENTCORE_MEMORY_ID,
            actorId=actor_id,
            sessionId=session_id,
            maxResults=100,
        )

        events = response.get("events", [])
        if not events:
            return None  # Empty — fall back to DDB (might have legacy data)

        messages = []
        for event in events:
            for payload_item in event.get("payload", []):
                conv = payload_item.get("conversational")
                if not conv:
                    continue
                role = conv.get("role", "").lower()
                if role not in ("user", "assistant"):
                    continue
                content_text = conv.get("content", {}).get("text", "")
                # Content is JSON-encoded by the session manager
                try:
                    import json as _json
                    parsed = _json.loads(content_text)
                    msg_content = parsed.get("message", {})
                    display_text = _extract_display_text(msg_content)
                    timestamp = parsed.get("created_at", event.get("eventTimestamp", ""))
                except (ValueError, KeyError, TypeError):
                    display_text = content_text
                    timestamp = event.get("eventTimestamp", "")

                if display_text:
                    messages.append({
                        "role": role,
                        "content": display_text,
                        "timestamp": str(timestamp),
                    })

                # Sort by timestamp (Memory returns newest-first, frontend expects oldest-first)
        messages.sort(key=lambda m: m.get("timestamp", ""))
        return messages if messages else None

    except Exception as e:
        logger.warning("Failed to read from AgentCore Memory, falling back to DDB: %s", e)
        return None


def get_session(session_id: str, email: str = ""):
    # Get session metadata first (needed for shared sessions)
    sess_table = dynamodb.Table(SESSIONS_TABLE)
    session_meta = None
    access = None

    if email:
        resp = sess_table.get_item(Key={"email": email, "session_id": session_id})
        session_meta = resp.get("Item")
        if session_meta:
            access = "owner"

    # If not found under this email, look up via GSI (shared session or public)
    if not session_meta:
        result = sess_table.query(
            IndexName="session-id-index",
            KeyConditionExpression=Key("session_id").eq(session_id),
            Limit=1,
        )
        items = result.get("Items", [])
        if items:
            session_meta = items[0]
            # Determine access level
            shared_with = session_meta.get("shared_with", []) or []
            if email in shared_with:
                access = "collaborator"
            elif session_meta.get("visibility") == "public":
                access = "viewer"
            else:
                return _response(403, {"error": "access denied"})

    if not session_meta:
        return _response(404, {"error": "session not found"})

    # For AgentCore Memory: use the owner's email as actorId (not the viewer's)
    memory_email = session_meta.get("email", email) if session_meta else email
    messages = _get_messages_from_memory(session_id, memory_email)

    if messages is None:
        # Fallback: read from DDB (legacy data or memory unavailable)
        msgs_table = dynamodb.Table(MESSAGES_TABLE)
        result = msgs_table.query(KeyConditionExpression=Key("session_id").eq(session_id))
        messages = result.get("Items", [])
        messages.sort(key=lambda m: m.get("timestamp", ""))

    files = session_meta.get("files", []) if session_meta else []
    shared_with = session_meta.get("shared_with", []) if session_meta else []
    vis = session_meta.get("visibility", "private") if session_meta else "private"

    return _response(200, {
        "session_id": session_id,
        "messages": messages,
        "files": files,
        "shared_with": shared_with if access != "viewer" else [],
        "access": access or "owner",
        "visibility": vis,
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
    # Read current shared_with, check for duplicates, then write
    resp = table.get_item(
        Key={"email": owner_email, "session_id": session_id},
        ProjectionExpression="session_id, shared_with",
    )
    item = resp.get("Item")
    if not item:
        return _response(404, {"error": "Session not found"})

    current_shared = item.get("shared_with", []) or []
    if share_with_email in current_shared:
        return _response(200, {"message": "Already shared", "shared_with": share_with_email})

    table.update_item(
        Key={"email": owner_email, "session_id": session_id},
        UpdateExpression="SET shared_with = list_append(if_not_exists(shared_with, :empty), :new_share)",
        ExpressionAttributeValues={
            ":new_share": [share_with_email],
            ":empty": [],
        },
    )

    return _response(200, {"message": "Session shared", "shared_with": share_with_email})


def set_visibility(event, email: str, session_id: str):
    """Set session visibility to public or private. Owner only."""
    body = json.loads(event.get("body") or "{}")
    new_visibility = body.get("visibility", "").strip().lower()

    if new_visibility not in ("public", "private"):
        return _response(400, {"error": "visibility must be 'public' or 'private'"})

    table = dynamodb.Table(SESSIONS_TABLE)

    # Verify ownership
    resp = table.get_item(
        Key={"email": email, "session_id": session_id},
        ProjectionExpression="session_id",
    )
    if not resp.get("Item"):
        return _response(403, {"error": "only the owner can change visibility"})

    table.update_item(
        Key={"email": email, "session_id": session_id},
        UpdateExpression="SET visibility = :v",
        ExpressionAttributeValues={":v": new_visibility},
    )

    return _response(200, {"message": "Visibility updated", "visibility": new_visibility})


def unshare_session(owner_email: str, session_id: str, target_email: str):
    """Remove a collaborator from a session. Owner only."""
    import urllib.parse
    target_email = urllib.parse.unquote(target_email).strip().lower()

    if not target_email:
        return _response(400, {"error": "email is required"})

    table = dynamodb.Table(SESSIONS_TABLE)

    # Verify ownership
    resp = table.get_item(
        Key={"email": owner_email, "session_id": session_id},
        ProjectionExpression="session_id, shared_with",
    )
    item = resp.get("Item")
    if not item:
        return _response(403, {"error": "only the owner can unshare"})

    current_shared = item.get("shared_with", []) or []
    if target_email not in current_shared:
        return _response(200, {"message": "Not shared with this email"})

    # Find the index and remove
    idx = current_shared.index(target_email)
    table.update_item(
        Key={"email": owner_email, "session_id": session_id},
        UpdateExpression=f"REMOVE shared_with[{idx}]",
    )

    return _response(200, {"message": "Collaborator removed", "removed": target_email})


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
    """Generate a presigned download URL for a file. Owner, collaborators, and viewers of public sessions allowed."""
    sess_table = dynamodb.Table(SESSIONS_TABLE)

    # Owner path
    session_meta = None
    if email:
        resp = sess_table.get_item(Key={"email": email, "session_id": session_id})
        session_meta = resp.get("Item")

    # Non-owner: query GSI and check access
    if not session_meta:
        result = sess_table.query(
            IndexName="session-id-index",
            KeyConditionExpression=Key("session_id").eq(session_id),
            Limit=1,
        )
        items = result.get("Items", [])
        if items:
            candidate = items[0]
            shared_with = candidate.get("shared_with", []) or []
            if email in shared_with or candidate.get("visibility") == "public":
                session_meta = candidate
            else:
                return _response(403, {"error": "access denied"})

    if not session_meta:
        return _response(404, {"error": "Session not found"})

    files = session_meta.get("files", [])
    target_file = next((f for f in files if f.get("file_id") == file_id), None)
    if not target_file:
        return _response(404, {"error": "File not found"})

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
            "Access-Control-Allow-Methods": "GET,POST,DELETE,PATCH,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }
