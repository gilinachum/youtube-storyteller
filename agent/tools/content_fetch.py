"""Firecrawl URL scraping tool for StoryTeller."""

import json
import boto3
import requests
from strands import tool

# In-memory cache for fetched URLs within a session
_url_cache: dict[str, str] = {}

# Secrets Manager client (lazy init)
_sm_client = None


def _get_secrets_client():
    global _sm_client
    if _sm_client is None:
        _sm_client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    return _sm_client


def _get_firecrawl_api_key() -> str:
    """Get Firecrawl API key from AWS Secrets Manager."""
    sm = _get_secrets_client()
    resp = sm.get_secret_value(SecretId="firecrawl/api-key")
    secret = resp["SecretString"]
    # Handle both plain string and JSON-wrapped secrets
    try:
        parsed = json.loads(secret)
        return parsed.get("api_key", parsed.get("apiKey", secret))
    except (json.JSONDecodeError, TypeError):
        return secret


@tool
def content_fetch(url: str) -> str:
    """Fetch and extract clean markdown content from a URL using Firecrawl.

    Use this tool when the user provides a URL and you need to extract its content
    for video planning. Results are cached to avoid re-fetching the same URL.

    Args:
        url: The URL to scrape and extract content from.

    Returns:
        Clean markdown text extracted from the URL.
    """
    # Check cache first
    if url in _url_cache:
        return f"[Cached] Content from {url}:\n\n{_url_cache[url]}"

    try:
        api_key = _get_firecrawl_api_key()

        response = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "formats": ["markdown"],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Extract markdown from response
        markdown = ""
        if "data" in data:
            markdown = data["data"].get("markdown", "")
        elif "markdown" in data:
            markdown = data["markdown"]

        if not markdown:
            markdown = f"[Warning] No markdown content extracted from {url}"

        # Cache the result
        _url_cache[url] = markdown

        return f"Content from {url}:\n\n{markdown}"

    except Exception as e:
        return f"[Error] Failed to fetch {url}: {str(e)}"
