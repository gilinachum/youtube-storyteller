"""Perplexity trend analysis tool for StoryTeller."""

import json
import boto3
import requests
from strands import tool
import os

_sm_client = None


def _get_secrets_client():
    global _sm_client
    if _sm_client is None:
        _sm_client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    return _sm_client


def _get_perplexity_api_key() -> str:
    """Get Perplexity API key from AWS Secrets Manager."""
    sm = _get_secrets_client()
    resp = sm.get_secret_value(SecretId="perplexity/api-key")
    secret = resp["SecretString"]
    try:
        parsed = json.loads(secret)
        return parsed.get("api_key", parsed.get("apiKey", secret))
    except (json.JSONDecodeError, TypeError):
        return secret


@tool
def trend_analysis(topic_area: str) -> str:
    """Perform deep research on what's trending in a topic area for YouTube virality.

    Use this tool to understand what's trending, what YouTube videos already exist,
    and what angles are underserved in a given topic area. This helps identify
    viral framing opportunities.

    Args:
        topic_area: The topic area to analyze trends for (e.g., "AWS AI agents", "serverless computing").

    Returns:
        Trend analysis including trending topics, existing videos, and underserved angles.
    """
    try:
        api_key = _get_perplexity_api_key()

        prompt = (
            f"Analyze current trends for YouTube content about: {topic_area}\n\n"
            "Please provide:\n"
            "1. What's currently trending in this topic area (last 30 days)?\n"
            "2. What similar YouTube videos already exist? List specific titles and channels if possible.\n"
            "3. What angles are underserved or haven't been covered well?\n"
            "4. What adjacent trending topics could be combined with this for broader appeal?\n"
            "5. What questions are people asking about this topic on forums, Reddit, Stack Overflow?\n"
            "6. Any upcoming events, launches, or announcements related to this topic?\n"
        )

        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a YouTube trend analyst specializing in tech content. "
                            "Provide detailed, actionable trend analysis with specific examples. "
                            "Focus on what would make a video go viral in this topic area."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        return f"Trend analysis for '{topic_area}':\n\n{content}"

    except Exception as e:
        return f"[Error] Trend analysis failed: {str(e)}"
