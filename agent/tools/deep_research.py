"""deep_research tool — parallel web + trend research with LLM summarization.

Runs web_research and trend_analysis concurrently, then uses Sonnet to
condense findings into a tight brief (~800 tokens). This keeps the main
agent's context manageable regardless of which model it uses.
"""

import os
import time
import logging
import concurrent.futures
from typing import Optional

import boto3
from strands import tool

from agent.tools import web_research, trend_analysis, content_fetch

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """You are a research summarizer for a YouTube video planning agent.
Condense the raw research below into a TIGHT brief (max 600 words) in THIS format:

## Key Facts
- (5-8 bullet points of most important findings)

## YouTube Landscape
- (what videos exist, what angles are covered, what gaps remain)

## Recommended Angles
1. (best angle for virality + why)
2. (second angle)
3. (third angle)

## Data Points for Script
- (specific numbers, stats, quotes that would make the video credible)

Be concise. No filler. Hebrew topic names stay in Hebrew, technical terms in English.

---
RAW RESEARCH:
"""


def _run_parallel_research(topic: str, urls: Optional[list] = None) -> dict:
    """Run web_research + trend_analysis in parallel using threads."""
    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        def _safe_web(t):
            try:
                return web_research(query=t, search_depth="advanced")
            except Exception as e:
                return f"[Error] web_research: {e}"

        def _safe_trend(t):
            try:
                return trend_analysis(topic_area=t)
            except Exception as e:
                return f"[Error] trend_analysis: {e}"

        def _safe_fetch(u):
            try:
                return content_fetch(url=u)
            except Exception as e:
                return f"[Error] content_fetch: {e}"

        futures['web_results'] = executor.submit(_safe_web, topic)
        futures['trend_results'] = executor.submit(_safe_trend, topic)

        if urls:
            for i, url in enumerate(urls[:3]):
                futures[f'url_{i}'] = executor.submit(_safe_fetch, url)

        # Collect results with timeouts
        timeouts = {'web_results': 15, 'trend_results': 20}
        for key, future in futures.items():
            timeout = timeouts.get(key, 15)
            try:
                results[key] = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                results[key] = f"[Timeout] {key} exceeded {timeout}s"
                logger.warning(f"Research tool {key} timed out after {timeout}s")
            except Exception as e:
                results[key] = f"[Error] {key}: {str(e)}"
                logger.warning(f"Research tool {key} failed: {e}")

    return results


def _summarize_with_sonnet(raw_research: str, topic: str) -> str:
    """Use Sonnet to condense raw research into a tight brief."""
    try:
        client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-west-2"))

        response = client.converse(
            modelId="us.amazon.nova-2-lite-v1:0",
            messages=[{
                "role": "user",
                "content": [{"text": f"{SUMMARIZE_PROMPT}\nTopic: {topic}\n\n{raw_research[:6000]}"}]
            }],
            inferenceConfig={"maxTokens": 1500, "temperature": 0.2},
        )

        output = response["output"]["message"]["content"][0]["text"]
        return output

    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        # Fallback: return truncated raw research
        return raw_research[:3000]


@tool
def deep_research(topic: str, urls: str = "") -> str:
    """חקור נושא חדש לעומק — מחקר אינטרנט וניתוח טרנדים במקביל.

    Use this tool to research a topic for video planning. It runs web search
    and trend analysis IN PARALLEL for speed, then summarizes findings into
    a concise brief. Returns key facts, YouTube landscape, recommended angles,
    and data points for scripting.

    Args:
        topic: The topic to research (e.g., "AWS Lambda SnapStart - what it is, when to use")
        urls: Optional comma-separated URLs to also fetch and include in research
    """
    t0 = time.time()

    # Parse URLs if provided
    url_list = [u.strip() for u in urls.split(",") if u.strip()] if urls else None

    # Step 1: Run tools in parallel (~10-15s)
    results = _run_parallel_research(topic, url_list)
    parallel_time = time.time() - t0

    # Step 2: Combine raw results
    raw_parts = []
    for key, val in results.items():
        if not val.startswith('['):
            raw_parts.append(f"### {key}\n{val[:3000]}")

    raw_research = "\n\n".join(raw_parts)

    # Step 3: Summarize with Sonnet (~3-5s)
    summary = _summarize_with_sonnet(raw_research, topic)
    total_time = time.time() - t0

    # Add timing and any errors
    header = f"# Research Brief: {topic}\n_Tools: {parallel_time:.1f}s | Summary: {total_time - parallel_time:.1f}s | Total: {total_time:.1f}s_\n"

    errors = [f"- {key}: {val}" for key, val in results.items() if val.startswith('[')]
    footer = ""
    if errors:
        footer = "\n## Notes\n" + "\n".join(errors)

    return f"{header}\n{summary}{footer}"
