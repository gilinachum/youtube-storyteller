"""Long-term memory retrieval for StoryTeller.

Retrieves relevant memories (session summaries + user preferences) from AgentCore Memory
using semantic search. Used to enrich the system prompt on session cold start.
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))


def _email_to_actor_id(email: str) -> str:
    """Convert email to valid AgentCore actorId."""
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")


def _get_client():
    """Get bedrock-agentcore data plane client."""
    return boto3.client("bedrock-agentcore", region_name=REGION)


def retrieve_long_term_memories(email: str, query_text: str) -> list[dict]:
    """Retrieve relevant long-term memories based on user's first message.

    Searches two namespaces:
    - Session summaries: what happened in past sessions
    - User preferences: content style, audience, thumbnail preferences

    Args:
        email: User's email address.
        query_text: The user's first message (used as semantic search query).

    Returns:
        List of memory record dicts with 'text', 'score', 'namespaces', 'strategy_id'.
        Empty list on any failure (non-blocking).
    """
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id:
        logger.debug("AGENTCORE_MEMORY_ID not configured — skipping memory retrieval")
        return []

    if not email or not query_text:
        return []

    actor_id = _email_to_actor_id(email)
    client = _get_client()
    records = []

    # Search session summaries
    try:
        response = client.retrieve_memory_records(
            memoryId=memory_id,
            namespacePath=f"/sessions/{actor_id}/",
            searchCriteria={
                "searchQuery": query_text,
                "topK": 3,
            },
        )
        for record in response.get("memoryRecordSummaries", []):
            records.append({
                "text": record.get("content", {}).get("text", ""),
                "score": record.get("score", 0),
                "namespaces": record.get("namespaces", []),
                "strategy_id": record.get("memoryStrategyId", ""),
            })
    except ClientError as e:
        logger.warning("Failed to retrieve session summaries: %s", e.response["Error"]["Code"])
    except Exception as e:
        logger.warning("Unexpected error retrieving session summaries: %s", e)

    # Search user preferences
    try:
        response = client.retrieve_memory_records(
            memoryId=memory_id,
            namespacePath=f"/users/{actor_id}/preferences/",
            searchCriteria={
                "searchQuery": query_text,
                "topK": 2,
            },
        )
        for record in response.get("memoryRecordSummaries", []):
            records.append({
                "text": record.get("content", {}).get("text", ""),
                "score": record.get("score", 0),
                "namespaces": record.get("namespaces", []),
                "strategy_id": record.get("memoryStrategyId", ""),
            })
    except ClientError as e:
        logger.warning("Failed to retrieve user preferences: %s", e.response["Error"]["Code"])
    except Exception as e:
        logger.warning("Unexpected error retrieving user preferences: %s", e)

    # Filter out empty records
    records = [r for r in records if r["text"].strip()]

    if records:
        logger.info("Retrieved %d long-term memory records for %s", len(records), actor_id)
    else:
        logger.debug("No long-term memories found for %s", actor_id)

    return records


def format_memories_for_prompt(memories: list[dict]) -> str:
    """Format memory records into a markdown block for system prompt injection.

    Args:
        memories: List of memory record dicts from retrieve_long_term_memories().

    Returns:
        Formatted markdown string, or empty string if no memories.
    """
    if not memories:
        return ""

    lines = [
        "# Retrieved Long-Term Memories",
        "",
        "The following memories from past conversations may be relevant to this session:",
        "",
    ]

    for i, mem in enumerate(memories, 1):
        text = mem["text"].strip()
        score = mem.get("score", 0)
        # Include score as a relevance hint (higher = more relevant)
        lines.append(f"{i}. (relevance: {score:.2f}) {text}")

    lines.append("")
    lines.append(
        "Use these memories naturally when relevant. "
        "Don't force-reference them if they don't apply to the current conversation."
    )
    lines.append("")

    return "\n".join(lines)
