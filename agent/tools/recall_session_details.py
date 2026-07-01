"""recall_session_details tool — loads a past session's full conversation and extracts specific details.

Uses a lightweight sub-agent to extract exactly what's asked for from the raw conversation history.
This enables cross-session references like "same thumbnail style as the K8s session".
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError
from strands import Agent, tool
from strands.models import BedrockModel

logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))
MAX_EXCHANGES = 50  # Cap loaded conversation to limit token usage


def _email_to_actor_id(email: str) -> str:
    """Convert email to valid AgentCore actorId."""
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")


def _load_session_conversation(memory_id: str, actor_id: str, session_id: str) -> list[str]:
    """Load all conversation turns from a session via short-term memory (list_events).

    Returns a list of strings like ["user: ...", "assistant: ..."].
    """
    client = boto3.client("bedrock-agentcore", region_name=REGION)

    events = []
    next_token = None
    while True:
        kwargs = {
            "memoryId": memory_id,
            "actorId": actor_id,
            "sessionId": session_id,
            "maxResults": 100,  # API cap
        }
        if next_token:
            kwargs["nextToken"] = next_token

        try:
            response = client.list_events(**kwargs)
        except ClientError as e:
            logger.error("Failed to list events for session %s: %s", session_id, e)
            return []

        events.extend(response.get("events", []))
        next_token = response.get("nextToken")
        if not next_token:
            break

    # Build conversation text from Converse-format events
    conversation = []
    for event in events:
        for payload in event.get("payload", []):
            conv = payload.get("conversational")
            if not conv:
                continue
            role = conv.get("role", "").lower()
            content_blocks = conv.get("content", [])
            # Content is a list of blocks (Converse format)
            if isinstance(content_blocks, list):
                for block in content_blocks:
                    text = block.get("text", "")
                    if role in ("user", "assistant") and text.strip():
                        conversation.append(f"{role}: {text}")
            elif isinstance(content_blocks, dict):
                # Fallback: single content dict
                text = content_blocks.get("text", "")
                if role in ("user", "assistant") and text.strip():
                    conversation.append(f"{role}: {text}")

    return conversation


def _get_extraction_agent() -> Agent:
    """Create a lightweight extraction sub-agent."""
    model = BedrockModel(
        model_id="us.amazon.nova-2-lite-v1:0",
        region_name=REGION,
        max_tokens=2000,
    )
    system_prompt = (
        "You are an extraction assistant. "
        "Given a conversation history and a query about specific details, "
        "extract exactly what's asked for. Be concise and structured. "
        "Return facts, not commentary. Use Hebrew if the source content is Hebrew."
    )
    return Agent(model=model, system_prompt=system_prompt, tools=[])


def make_recall_session_details_tool(email: str):
    """Factory returning a recall_session_details tool bound to the user's email."""

    @tool
    def recall_session_details(session_id: str, query: str) -> dict:
        """Load full conversation from a past session and extract specific details.

        Use this when the user references something from a specific past session
        (e.g., "same thumbnail style as the K8s session"). First identify the session ID
        from long-term memory context, then call this tool with the session_id and
        a precise description of what details to extract.

        Args:
            session_id: The AgentCore session ID (found in long-term memory summaries).
            query: What details to extract (e.g., "thumbnail design: colors, fonts, layout, prompt used").

        Returns:
            Dict with extracted details, or error information.
        """
        memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
        if not memory_id:
            return {"error": "AgentCore Memory not configured"}

        if not session_id or not query:
            return {"error": "Both session_id and query are required"}

        actor_id = _email_to_actor_id(email)

        # Load conversation from short-term memory
        conversation = _load_session_conversation(memory_id, actor_id, session_id)

        if not conversation:
            return {
                "error": f"No conversation found for session {session_id}",
                "session_id": session_id,
            }

        # Cap conversation length
        capped = conversation[:MAX_EXCHANGES * 2]  # Each exchange = user + assistant

        # Extract details via sub-agent
        try:
            agent = _get_extraction_agent()
            prompt = (
                f"Extract the following details from this conversation:\n"
                f"Query: {query}\n\n"
                f"Conversation ({len(capped)} messages):\n"
                + "\n".join(capped)
                + "\n\nReturn only the extracted details."
            )

            result = agent(prompt)
            extracted_text = str(result)

            return {
                "session_id": session_id,
                "query": query,
                "extracted": extracted_text,
                "event_count": len(conversation),
            }

        except Exception as e:
            logger.error("Extraction sub-agent failed for session %s: %s", session_id, e, exc_info=True)
            return {
                "error": f"Extraction failed: {str(e)}",
                "session_id": session_id,
                "event_count": len(conversation),
            }

    return recall_session_details
