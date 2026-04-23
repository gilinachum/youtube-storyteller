"""Chat handler — async pattern for long-running Strands agent.

Flow:
  POST /chat  → triggers async Lambda invocation → returns job_id immediately
  GET  /chat/{job_id} → polls DynamoDB for result

This avoids the API Gateway 29s hard timeout.
"""
import json
import os
import uuid
import boto3
from datetime import datetime, timezone

MESSAGES_TABLE = os.environ.get("MESSAGES_TABLE", "storyteller-messages")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
JOBS_TABLE = os.environ.get("JOBS_TABLE", "storyteller-jobs")
SELF_FUNCTION_NAME = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "storyteller-chat")

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
lambda_client = boto3.client("lambda", region_name="us-east-1")


def handler(event, context):
    """Route: POST /chat or GET /chat/{job_id} or internal async invoke."""

    # Internal async invocation (no API Gateway envelope)
    if event.get("_async"):
        return _run_agent_async(event)

    method = event.get("httpMethod", "POST")
    path_params = event.get("pathParameters") or {}
    job_id = path_params.get("job_id")

    if method == "GET" and job_id:
        return _poll_job(job_id)

    # POST /chat — kick off async job
    try:
        body = json.loads(event.get("body") or "{}")
        email = body.get("email", "").strip().lower()
        message = body.get("message", "").strip()
        session_id = body.get("session_id") or str(uuid.uuid4())

        if not email:
            return _response(403, {"error": "Email required"})
        if not message:
            return _response(400, {"error": "message is required"})

        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Write pending job record
        _write_job(job_id, session_id, email, "pending", now)

        # Async self-invocation
        lambda_client.invoke(
            FunctionName=SELF_FUNCTION_NAME,
            InvocationType="Event",  # fire-and-forget
            Payload=json.dumps({
                "_async": True,
                "job_id": job_id,
                "session_id": session_id,
                "email": email,
                "message": message,
                "started_at": now,
            }),
        )

        return _response(202, {
            "job_id": job_id,
            "session_id": session_id,
            "status": "pending",
            "poll_url": f"/chat/{job_id}",
        })

    except Exception as e:
        import traceback
        return _response(500, {"error": str(e), "trace": traceback.format_exc()})


def _run_agent_async(event):
    """Execute the Strands agent and write result to DynamoDB."""
    job_id = event["job_id"]
    session_id = event["session_id"]
    email = event["email"]
    message = event["message"]

    def update_progress(step: str):
        """Write a progress update to the jobs table."""
        try:
            jobs = dynamodb.Table(JOBS_TABLE)
            jobs.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET progress = :p, updated_at = :now",
                ExpressionAttributeValues={
                    ":p": step,
                    ":now": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass  # best-effort

    try:
        import sys
        sys.path.insert(0, "/var/task")
        from agent.main import create_agent
        from boto3.dynamodb.conditions import Key

        update_progress("מתחיל לעבד...")

        # Load history
        msgs_table = dynamodb.Table(MESSAGES_TABLE)
        result = msgs_table.query(
            KeyConditionExpression=Key("session_id").eq(session_id),
            Limit=20,
            ScanIndexForward=False,
        )
        history = list(reversed(result.get("Items", [])))
        history_text = "\n".join([
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in history[-10:]
        ])

        if history_text:
            full_prompt = f"[Previous conversation:\n{history_text}\n]\n\nUser: {message}"
        else:
            full_prompt = message

        update_progress("חוקר ומנתח את הנושא...")

        # Create agent with progress callback
        agent = create_agent()

        # Hook into tool calls for progress updates
        import strands
        original_call = agent.__call__

        # We'll use the agent's callback handler to track tool usage
        # For now, update progress based on tool execution logs
        update_progress("מריץ את האייג'נט...")

        response = agent(full_prompt)
        agent_response = str(response)

        update_progress("מסכם תשובה...")

        now = datetime.now(timezone.utc).isoformat()

        # Save messages
        msgs_table.put_item(Item={"session_id": session_id, "timestamp": event["started_at"], "role": "user", "content": message})
        msgs_table.put_item(Item={"session_id": session_id, "timestamp": now, "role": "assistant", "content": agent_response})

        # Ensure session record
        _ensure_session(email, session_id, now)

        # Update job as complete
        _write_job(job_id, session_id, email, "complete", now, response=agent_response)

    except Exception as e:
        import traceback
        now = datetime.now(timezone.utc).isoformat()
        _write_job(job_id, session_id, email, "error", now, error=f"{e}\n{traceback.format_exc()}")


def _poll_job(job_id: str):
    """Return current job status from DynamoDB."""
    try:
        table = dynamodb.Table(JOBS_TABLE)
        item = table.get_item(Key={"job_id": job_id}).get("Item")
        if not item:
            return _response(404, {"error": "job not found"})
        return _response(200, {
            "job_id": job_id,
            "status": item.get("status"),
            "session_id": item.get("session_id"),
            "response": item.get("response"),
            "error": item.get("error"),
            "progress": item.get("progress"),
        })
    except Exception as e:
        return _response(500, {"error": str(e)})


def _write_job(job_id, session_id, email, status, timestamp, response=None, error=None):
    table = dynamodb.Table(JOBS_TABLE)
    item = {
        "job_id": job_id,
        "session_id": session_id,
        "email": email,
        "status": status,
        "updated_at": timestamp,
    }
    if response is not None:
        item["response"] = response
    if error is not None:
        item["error"] = error
    table.put_item(Item=item)


def _ensure_session(email, session_id, now):
    table = dynamodb.Table(SESSIONS_TABLE)
    try:
        table.put_item(
            Item={"email": email, "session_id": session_id, "name": "שיחה חדשה", "created_at": now, "updated_at": now, "status": "active", "language": "he"},
            ConditionExpression="attribute_not_exists(session_id)",
        )
    except Exception:
        table.update_item(
            Key={"email": email, "session_id": session_id},
            UpdateExpression="SET updated_at = :now",
            ExpressionAttributeValues={":now": now},
        )


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=str),
    }
