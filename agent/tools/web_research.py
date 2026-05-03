"""Tavily web search tool for StoryTeller."""

import json
import boto3
import requests
from strands import tool

_sm_client = None


def _get_secrets_client():
    global _sm_client
    if _sm_client is None:
        _sm_client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    return _sm_client


def _get_tavily_api_key() -> str:
    """Get Tavily API key from AWS Secrets Manager."""
    sm = _get_secrets_client()
    resp = sm.get_secret_value(SecretId="tavily/api-key")
    secret = resp["SecretString"]
    try:
        parsed = json.loads(secret)
        return parsed.get("api_key", parsed.get("apiKey", secret))
    except (json.JSONDecodeError, TypeError):
        return secret


@tool
def web_research(query: str, search_depth: str = "advanced") -> str:
    """Search the web for context, trends, and competitive landscape using Tavily.

    Use this tool to research a topic before planning a video. It returns
    relevant search results with content snippets from current web sources
    including YouTube videos, blog posts, documentation, and discussions.

    Args:
        query: The search query — be specific about what you want to learn.
        search_depth: Search depth - "basic" for quick lookups, "advanced" for thorough research (default: advanced).

    Returns:
        Search results with titles, URLs, and content snippets.
    """
    try:
        api_key = _get_tavily_api_key()

        response = requests.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": search_depth,
                "max_results": 10,
                "include_answer": True,
                "include_raw_content": False,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        parts = []

        # Include Tavily's synthesized answer if available
        if data.get("answer"):
            parts.append(f"**Summary:** {data['answer']}")
            parts.append("")

        # Include individual results
        results = data.get("results", [])
        if results:
            parts.append(f"**Sources ({len(results)} results):**")
            parts.append("")
            for i, r in enumerate(results, 1):
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                content = r.get("content", "")[:500]
                score = r.get("score", 0)
                parts.append(f"### {i}. {title}")
                parts.append(f"URL: {url}")
                parts.append(f"Relevance: {score:.2f}")
                parts.append(f"{content}")
                parts.append("")

        if not parts:
            return f"No results found for '{query}'"

        return f"Web research for '{query}':\n\n" + "\n".join(parts)

    except Exception as e:
        return f"[Error] Web research failed: {str(e)}"
