"""Web search tool for StoryTeller — via AgentCore Gateway Web Search Tool.

Replaces the previous Tavily integration (api.tavily.com). Calls stay
inside AWS (no third-party egress); the Gateway is a single shared
resource in us-east-1 regardless of stage (see infra/stacks/gateway_search_stack.py
for why — the Web Search Tool connector is us-east-1-only today).

Note: unlike Tavily, Web Search Tool returns only ranked results (title,
url, snippet, publishedDate) with no synthesized "answer" field. This tool
does not attempt to backfill a synthesized summary — deep_research.py's
Nova 2 Lite summarization step is responsible for turning raw results
(from this tool and from trend_analysis.py) into the final brief.

Per the Web Search Tool's acceptable-use terms, any user-facing output
that uses these results MUST retain the source citations/links.
"""
import json
import logging
import os

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from strands import tool

logger = logging.getLogger(__name__)

GATEWAY_URL = os.environ["SEARCH_GATEWAY_URL"]
GATEWAY_REGION = "us-east-1"  # Web Search Tool connector is us-east-1-only today
WEB_SEARCH_TOOL_NAME = "web-search-tool___WebSearch"  # <target-name>___<tool-name>


def _mcp_call(method: str, params: dict, request_id: int = 1, timeout: int = 20) -> dict:
    """Minimal synchronous MCP JSON-RPC call over HTTPS, SigV4-signed (AWS_IAM gateway auth)."""
    body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
    request = AWSRequest(
        method="POST",
        url=GATEWAY_URL,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    creds = boto3.Session().get_credentials()
    SigV4Auth(creds, "bedrock-agentcore", GATEWAY_REGION).add_auth(request)
    signed_headers = dict(request.headers.items())

    resp = requests.post(GATEWAY_URL, data=body, headers=signed_headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


@tool
def web_research(query: str, search_depth: str = "advanced") -> str:
    """Search the web for context, trends, and competitive landscape.

    Use this tool to research a topic before planning a video. It returns
    relevant search results with content snippets from current web sources
    including YouTube videos, blog posts, documentation, and discussions.

    Args:
        query: The search query — be specific about what you want to learn.
        search_depth: Accepted for backward compatibility with callers; the
            Web Search Tool backend has no depth parameter, so this is
            currently unused.

    Returns:
        Search results with titles, URLs, snippets, and publish dates.
        Always preserve the source URL when citing a fact from these
        results in user-facing output.
    """
    try:
        result = _mcp_call(
            "tools/call",
            {
                "name": WEB_SEARCH_TOOL_NAME,
                "arguments": {"query": query[:200], "maxResults": 10},
            },
        )

        if "error" in result:
            return f"[Error] Web research failed: {result['error']}"

        content = result.get("result", {}).get("content", [])
        text_block = next((c["text"] for c in content if c.get("type") == "text"), None)
        if not text_block:
            return f"No results found for '{query}'"

        payload = json.loads(text_block)
        results = payload.get("results", [])

        if not results:
            return f"No results found for '{query}'"

        parts = [f"**Sources ({len(results)} results):**", ""]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            snippet = r.get("text", "")[:500]
            published = r.get("publishedDate", "")
            parts.append(f"### {i}. {title}")
            parts.append(f"URL: {url}")
            if published:
                parts.append(f"Published: {published}")
            parts.append(snippet)
            parts.append("")

        return f"Web research for '{query}':\n\n" + "\n".join(parts)

    except Exception as e:
        logger.error(f"Web research (Gateway Web Search) failed: {e}")
        return f"[Error] Web research failed: {str(e)}"
