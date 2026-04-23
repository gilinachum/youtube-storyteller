"""Upload handler — generate presigned S3 URL and track files in DynamoDB."""
import json
import os
import uuid
from datetime import datetime, timezone
import boto3


UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")

s3 = boto3.client("s3", region_name="us-east-1")
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".ppt", ".txt", ".md", ".doc", ".docx"}
MAX_SIZE_MB = 50


def handler(event, context):
    try:
        method = event.get("httpMethod", "POST")
        path_params = event.get("pathParameters") or {}

        if method == "DELETE":
            return delete_file(event)
        elif method == "GET":
            return list_files(event)

        # POST — upload
        body = json.loads(event.get("body") or "{}")
        email = body.get("email", "").strip().lower()
        session_id = body.get("session_id", "").strip()
        filename = body.get("filename", "upload").strip()
        content_type = body.get("content_type", "application/octet-stream")

        if not email or not session_id:
            return _response(400, {"error": "email and session_id are required"})

        # Validate extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return _response(400, {
                "error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            })

        # Generate S3 key
        file_id = str(uuid.uuid4())[:8]
        s3_key = f"uploads/{email}/{session_id}/{file_id}-{filename}"

        # Generate presigned URL (valid 15 minutes)
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": UPLOAD_BUCKET,
                "Key": s3_key,
                "ContentType": content_type,
            },
            ExpiresIn=900,
        )

        # Track file in DynamoDB (session metadata)
        now = datetime.now(timezone.utc).isoformat()
        _record_file(email, session_id, file_id, filename, s3_key, content_type, now)

        return _response(200, {
            "upload_url": upload_url,
            "key": s3_key,
            "file_id": file_id,
        })

    except Exception as e:
        return _response(500, {"error": str(e)})


def list_files(event):
    """GET /upload?session_id=xxx — list files for a session."""
    query_params = event.get("queryStringParameters") or {}
    session_id = query_params.get("session_id", "")
    email = query_params.get("email", "")
    if not session_id or not email:
        return _response(400, {"error": "email and session_id query params required"})

    table = dynamodb.Table(SESSIONS_TABLE)
    result = table.get_item(Key={"email": email, "session_id": session_id})
    item = result.get("Item", {})
    files = item.get("files", [])
    return _response(200, {"files": files})


def delete_file(event):
    """DELETE /upload — remove a file from S3 and DynamoDB."""
    body = json.loads(event.get("body") or "{}")
    email = body.get("email", "").strip().lower()
    session_id = body.get("session_id", "").strip()
    file_id = body.get("file_id", "").strip()
    s3_key = body.get("key", "").strip()

    if not email or not session_id or not file_id:
        return _response(400, {"error": "email, session_id, and file_id are required"})

    # Delete from S3
    if s3_key:
        try:
            s3.delete_object(Bucket=UPLOAD_BUCKET, Key=s3_key)
        except Exception:
            pass  # best-effort

    # Remove from DynamoDB session record
    table = dynamodb.Table(SESSIONS_TABLE)
    result = table.get_item(Key={"email": email, "session_id": session_id})
    item = result.get("Item", {})
    files = [f for f in item.get("files", []) if f.get("file_id") != file_id]
    table.update_item(
        Key={"email": email, "session_id": session_id},
        UpdateExpression="SET files = :f",
        ExpressionAttributeValues={":f": files},
    )
    return _response(200, {"deleted": file_id})


def _record_file(email, session_id, file_id, filename, s3_key, content_type, timestamp):
    """Append file record to the session's files list in DynamoDB."""
    table = dynamodb.Table(SESSIONS_TABLE)
    file_record = {
        "file_id": file_id,
        "filename": filename,
        "s3_key": s3_key,
        "content_type": content_type,
        "uploaded_at": timestamp,
    }
    # Try to append to existing files list
    try:
        table.update_item(
            Key={"email": email, "session_id": session_id},
            UpdateExpression="SET files = list_append(if_not_exists(files, :empty), :new_file), updated_at = :now",
            ExpressionAttributeValues={
                ":new_file": [file_record],
                ":empty": [],
                ":now": timestamp,
            },
        )
    except Exception:
        # Session might not exist yet — create it
        table.put_item(Item={
            "email": email,
            "session_id": session_id,
            "name": "שיחה חדשה",
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": "active",
            "language": "he",
            "files": [file_record],
        })


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
