"""StoryTeller - AgentCore Runtime entrypoint.

Wraps the Strands agent with BedrockAgentCoreApp for deployment on AgentCore Runtime.
Each runtime session gets its own process - we keep the Agent instance alive for the
session lifetime. On cold start (new session or session restart), we reload conversation
history from DynamoDB.

Supports both sync (dict return) and streaming (async generator) modes.
The /invocations endpoint with streaming uses the async generator path.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.main import create_agent

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── AgentCore Observability ──────────────────────────────────────────────────
# AgentCore Runtime auto-instruments the agent via ADOT (aws-opentelemetry-distro)
# when observability.enabled=true in .bedrock_agentcore.yaml. No manual setup needed.
# Strands emits OTEL traces via strands-agents[otel]. CloudWatch Transaction Search
# must be enabled (one-time) to view traces in the GenAI Observability dashboard.

# ── DynamoDB tables ──────────────────────────────────────────────────────────
MESSAGES_TABLE = os.environ.get("MESSAGES_TABLE", "storyteller-messages")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "storyteller-sessions")
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))

dynamodb = boto3.resource("dynamodb", region_name=REGION)

# ── In-process agent cache ───────────────────────────────────────────────────
_agents: dict[str, "Agent"] = {}

app = BedrockAgentCoreApp()


def _load_history(app_session_id: str) -> list[dict]:
    """Load conversation history from DynamoDB messages table."""
    table = dynamodb.Table(MESSAGES_TABLE)
    items = []
    last_key = None
    while True:
        kwargs = {
            "KeyConditionExpression": Key("session_id").eq(app_session_id),
            "ScanIndexForward": True,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        result = table.query(**kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
    return items


def _inject_history(agent, history_items: list[dict]):
    """Inject DynamoDB message history into a fresh Strands agent."""
    for item in history_items:
        role = item.get("role", "user")
        content = item.get("content", "")
        agent.messages.append({
            "role": role,
            "content": [{"text": content}],
        })


def _save_message(app_session_id: str, role: str, content: str, timestamp: str):
    """Persist a single message to DynamoDB."""
    table = dynamodb.Table(MESSAGES_TABLE)
    table.put_item(Item={
        "session_id": app_session_id,
        "timestamp": timestamp,
        "role": role,
        "content": content,
    })


def _ensure_session(email: str, app_session_id: str, now: str):
    """Create or update the session record."""
    table = dynamodb.Table(SESSIONS_TABLE)
    try:
        table.put_item(
            Item={
                "email": email,
                "session_id": app_session_id,
                "name": "שיחה חדשה",
                "created_at": now,
                "updated_at": now,
                "status": "active",
                "language": "he",
            },
            ConditionExpression="attribute_not_exists(session_id)",
        )
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        # Session already exists — just bump updated_at (expected on 2nd+ message)
        table.update_item(
            Key={"email": email, "session_id": app_session_id},
            UpdateExpression="SET updated_at = :now",
            ExpressionAttributeValues={":now": now},
        )


def _get_or_create_agent(email: str, app_session_id: str, first_message: str = None) -> "Agent":
    """Get an existing agent or create one and reload history.
    
    On cache miss (cold start), creates a new agent. If first_message is provided,
    long-term memories are retrieved and injected into the system prompt.
    On cache hit, returns the existing agent (memories already in prompt).
    """
    cache_key = f"{email}:{app_session_id}"

    if cache_key in _agents:
        return _agents[cache_key]

    logger.info("Cold start for session %s", app_session_id)
    agent = create_agent(email=email, session_id=app_session_id, user_message=first_message)

    # If session manager is active, it handles history loading automatically.
    # Only fall back to manual DDB history injection if no session manager.
    if not getattr(agent, '_session_manager', None):
        logger.info("No session manager — loading history from DynamoDB for session %s", app_session_id)
        history = _load_history(app_session_id)
        if history:
            logger.info("Loaded %d messages from DynamoDB for session %s", len(history), app_session_id)
            _inject_history(agent, history)
        else:
            logger.info("New session %s - no history to load", app_session_id)
    else:
        logger.info("Session manager active — history will be loaded automatically for session %s", app_session_id)

    _agents[cache_key] = agent
    return agent


def _extract_email_from_jwt(context) -> str:
    """Extract email from JWT in the Authorization header.
    
    Requires requestHeaderAllowlist=["Authorization"] on the AgentCore runtime
    so the header is forwarded to the handler via context.request_headers.
    """
    try:
        import base64
        
        # AgentCore SDK passes allowed headers via context.request_headers dict
        headers = getattr(context, "request_headers", None) or {}
        
        # Fallback: try the Starlette request object
        if not headers:
            request = getattr(context, "request", None)
            if request and hasattr(request, "headers"):
                headers = dict(request.headers)
        
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        if not auth:
            logger.warning("No Authorization header in context.request_headers")
            return ""
        
        token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else auth
        if "." not in token:
            logger.warning("Authorization header is not a JWT")
            return ""
        
        # Decode JWT payload without verification (already validated by AgentCore)
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        
        email = claims.get("email", claims.get("sub", "")).strip().lower()
        if email:
            logger.info(f"Extracted email from JWT: {email}")
        return email
    except Exception as e:
        logger.warning(f"Failed to extract email from JWT: {e}")
    return ""


def _parse_payload(payload: dict, context=None) -> tuple[str, str, str, list, str]:
    """Parse and validate the invocation payload.

    Returns (email, message, app_session_id, file_refs, full_prompt).
    Raises ValueError on missing required fields.
    """
    email = payload.get("email", "").strip().lower()
    # Fallback: extract email from JWT if not in payload (Cognito auth mode)
    if not email and context:
        email = _extract_email_from_jwt(context)
    message = payload.get("message", "").strip()
    app_session_id = payload.get("session_id", "")
    file_refs = payload.get("file_refs", [])

    if not email:
        raise ValueError("email is required (send in body or via JWT)")
    if not message:
        raise ValueError("message is required")
    if not app_session_id:
        raise ValueError("session_id is required")

    full_prompt = message
    if file_refs:
        refs_text = "\n".join(
            [f"[קובץ מצורף: {f['filename']} ({f['s3_key']})]" for f in file_refs]
        )
        full_prompt = f"{refs_text}\n\n{message}"

    return email, message, app_session_id, file_refs, full_prompt


@app.entrypoint
async def invoke(payload, context):
    """Main entrypoint - returns async generator for streaming.

    Expected payload:
    {
        "email": "user@example.com",
        "message": "I want to make a video about...",
        "session_id": "app-level-session-uuid"
    }

    Yields text chunks as they stream from the agent.
    The full response is persisted to DynamoDB after streaming completes.
    """
    try:
        email, message, app_session_id, file_refs, full_prompt = _parse_payload(payload, context)
    except ValueError as e:
        # For validation errors, yield error as a single chunk
        # Capture e immediately - Python 3.13 deletes it after except block
        error_msg = str(e)
        async def error_stream():
            yield json.dumps({"error": error_msg})
        return error_stream()

    now = datetime.now(timezone.utc).isoformat()

    # Get or create agent with history
    agent = _get_or_create_agent(email, app_session_id, first_message=full_prompt)

    # Ensure session record exists
    _ensure_session(email, app_session_id, now)

    # Save user message — only if no session manager (it handles persistence)
    has_session_manager = getattr(agent, '_session_manager', None) is not None
    if not has_session_manager:
        _save_message(app_session_id, "user", full_prompt, now)

    # Tool name to Hebrew progress label mapping
    TOOL_LABELS = {
        "content_fetch": "🔗 מביא תוכן מהאינטרנט...",
        "pdf_extract": "📄 מנתח קובץ PDF...",
        "pptx_extract": "📊 מנתח מצגת...",
        "web_research": "🔍 מחפש באינטרנט...",
        "trend_analysis": "📈 בודק טרנדים...",
        "name_session": "✏️ שומר שיחה...",
        "export_document": "📝 מכין מסמך...",
        "design_thumbnail": "🎨 מעצב טאמבנייל...",
        "save_user_photo": "🖼️ שומר תמונת פרופיל...",
    }

    async def generate_stream():
        """Stream agent response chunks, then persist the full response."""
        import asyncio

        full_response = []
        keepalive_queue: asyncio.Queue = asyncio.Queue()
        stream_done = False

        async def keepalive_sender():
            """Send keepalive markers every 10s while stream is active."""
            while not stream_done:
                await asyncio.sleep(10)
                if not stream_done:
                    await keepalive_queue.put("__KEEPALIVE__")

        # Start keepalive task
        keepalive_task = asyncio.ensure_future(keepalive_sender())

        try:
            # Wrap agent stream as async iterator with interleaved keepalives
            agent_iter = agent.stream_async(full_prompt).__aiter__()
            agent_exhausted = False

            while not agent_exhausted:
                # Race between next agent event and keepalive
                try:
                    # Create a future for the next agent event
                    agent_next = asyncio.ensure_future(agent_iter.__anext__())

                    while True:
                        # Check for keepalive first (non-blocking)
                        try:
                            ka = keepalive_queue.get_nowait()
                            yield ka
                        except asyncio.QueueEmpty:
                            pass

                        # Wait for agent event with short timeout
                        try:
                            event = await asyncio.wait_for(asyncio.shield(agent_next), timeout=5.0)
                            break  # Got an agent event
                        except asyncio.TimeoutError:
                            # No agent event yet - yield keepalive
                            yield "__KEEPALIVE__"
                            continue

                    # Process the agent event
                    if "data" in event:
                        chunk = event["data"]
                        full_response.append(chunk)
                        yield chunk

                    # Detect tool use start - emit progress event
                    tool_use = (
                        event.get("event", {})
                        .get("contentBlockStart", {})
                        .get("start", {})
                        .get("toolUse")
                    )
                    if tool_use:
                        tool_name = tool_use.get("name", "")
                        label = TOOL_LABELS.get(tool_name, f"\u2699\ufe0f {tool_name}...")
                        progress_json = json.dumps({"type": "progress", "tool": tool_name, "label": label}, ensure_ascii=False)
                        yield f"__PROGRESS__{progress_json}"

                except StopAsyncIteration:
                    agent_exhausted = True
        except Exception as e:
            logger.error("Agent streaming failed: %s", e, exc_info=True)
            error_msg = f"שגיאה בעיבוד הבקשה: {str(e)}"
            full_response.append(error_msg)
            yield error_msg
        finally:
            stream_done = True
            keepalive_task.cancel()
            try:
                await keepalive_task
            except (asyncio.CancelledError, Exception):
                pass

        # Persist the complete response — only if no session manager
        complete_response = "".join(full_response)
        resp_time = datetime.now(timezone.utc).isoformat()
        if not has_session_manager:
            _save_message(app_session_id, "assistant", complete_response, resp_time)
        _ensure_session(email, app_session_id, resp_time)

        logger.info(
            "Streaming complete for session %s - %d chars",
            app_session_id,
            len(complete_response),
        )

    return generate_stream()


if __name__ == "__main__":
    app.run()
