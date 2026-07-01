"""Research agent for StoryTeller — runs web research + trend analysis in parallel.

Can be run standalone for local testing:
    python -m agent.research_agent "AWS Lambda SnapStart"
"""

import os
import sys
import asyncio
import concurrent.futures
import logging
from typing import Optional

from strands import Agent
from strands.models import BedrockModel, CacheConfig

from agent.tools import (
    content_fetch,
    web_research,
    trend_analysis,
)
from agent.model_config import get_model_config, ModelConfig

logger = logging.getLogger(__name__)


RESEARCH_SYSTEM_PROMPT = """# Role

You are a **Research Assistant** — a fast, thorough researcher supporting a YouTube video planning agent.
Your job is to gather comprehensive information about a topic from multiple sources.

# Instructions

When given a research task:

1. **Run multiple research tools in parallel** when possible:
   - Use `web_research` to find current information, news, and context
   - Use `trend_analysis` to understand what's trending and what angles work
   - Use `content_fetch` to scrape specific URLs if provided

2. **Synthesize findings** into a structured research brief:
   - Key facts and data points
   - Current state of the topic (what's new, what changed)
   - Competing/related YouTube videos (if found)
   - Interesting angles or hooks for video content
   - Any controversies or sensitivities to be aware of

3. **Be thorough but fast** — gather what's needed, don't over-research.

4. **Output in English** — the parent agent will translate to Hebrew.

5. **Include sources** — mention where key facts came from.

# Important
- Focus on ACTIONABLE insights for video planning
- Flag if a topic is too niche (low search interest) or too broad
- Note if the topic has strong YouTube competition already
- Suggest unique angles that aren't already covered
"""


def _run_parallel_research(topic: str, urls: Optional[list] = None) -> dict:
    """Run web_research + trend_analysis in parallel using threads.
    
    Returns dict with keys: web_results, trend_results, url_results
    """
    results = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        
        # Always run web search (call decorated tool directly)
        futures['web_results'] = executor.submit(
            web_research, query=topic, search_depth="advanced"
        )
        
        # Always run trend analysis
        futures['trend_results'] = executor.submit(
            trend_analysis, topic_area=topic
        )
        
        # Fetch URLs if provided
        if urls:
            for i, url in enumerate(urls[:3]):  # Max 3 URLs
                futures[f'url_{i}'] = executor.submit(
                    content_fetch, url=url
                )
        
        # Collect results with timeout (web=15s, trend=25s)
        timeouts = {'web_results': 15, 'trend_results': 25}
        for key, future in futures.items():
            timeout = timeouts.get(key, 20)
            try:
                results[key] = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                results[key] = f"[Timeout] {key} exceeded {timeout}s"
                logger.warning(f"Research tool {key} timed out after {timeout}s")
            except Exception as e:
                results[key] = f"[Error] {key}: {str(e)}"
                logger.warning(f"Research tool {key} failed: {e}")
    
    return results


def create_research_agent(model_provider: Optional[str] = None) -> Agent:
    """Create a research sub-agent with web tools.
    
    Args:
        model_provider: Override model provider ('bedrock' or 'mantle'). 
                       Defaults to env RESEARCH_MODEL_PROVIDER or 'bedrock'.
    """
    provider = model_provider or os.environ.get("RESEARCH_MODEL_PROVIDER", "bedrock")
    
    if provider == "mantle":
        # Use Grok for research too
        model_cfg = get_model_config("mantle")
        from strands.models.openai import OpenAIModel
        import boto3
        
        sm = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-west-2"))
        secret = sm.get_secret_value(SecretId="bedrock/mantle-api-key")
        api_key = secret["SecretString"]
        
        region = os.environ.get("MANTLE_REGION", "us-east-1")
        model = OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": f"https://bedrock-mantle.{region}.api.aws/openai/v1",
            },
            model_id=model_cfg.model_id,
            max_tokens=8192,
        )
    else:
        # Default: Sonnet on Bedrock
        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-6",
            region_name=os.environ.get("AWS_REGION", "us-west-2"),
            max_tokens=8192,
            cache_config=CacheConfig(strategy="auto"),
            cache_tools="default",
        )

    # Use ConcurrentToolExecutor for parallel tool calls
    from strands.tools.executors.concurrent import ConcurrentToolExecutor
    
    return Agent(
        name="research_assistant",
        description=(
            "Research a topic thoroughly for YouTube video planning. "
            "Gathers web research, trend analysis, and URL content IN PARALLEL. "
            "Pass a topic description and optional URLs to research. "
            "Returns a structured research brief with key findings, trends, "
            "angles, and sources."
        ),
        model=model,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        tools=[
            content_fetch,
            web_research,
            trend_analysis,
        ],
        tool_executor=ConcurrentToolExecutor(),
    )


# --- Local CLI runner ---

def main():
    """Run research agent locally for testing."""
    if len(sys.argv) < 2:
        print("Usage: python -m agent.research_agent <topic> [--parallel] [--provider bedrock|mantle]")
        sys.exit(1)
    
    # Parse args
    args = sys.argv[1:]
    parallel_mode = "--parallel" in args
    provider = "bedrock"
    if "--provider" in args:
        idx = args.index("--provider")
        provider = args[idx + 1]
        args = [a for i, a in enumerate(args) if i != idx and i != idx + 1]
    args = [a for a in args if a != "--parallel"]
    topic = " ".join(args)
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    
    print(f"\n{'='*60}")
    print(f"StoryTeller Research Agent — Local Test")
    print(f"Topic: {topic}")
    print(f"Provider: {provider}")
    print(f"Parallel direct: {parallel_mode}")
    print(f"{'='*60}\n")
    
    import time
    t0 = time.time()
    
    if parallel_mode:
        # Skip the agent entirely — run tools directly in parallel
        print("🔄 Running tools in parallel (bypassing agent)...")
        results = _run_parallel_research(topic)
        elapsed = time.time() - t0
        print(f"\n⏱️  Parallel research completed in {elapsed:.1f}s\n")
        for key, val in results.items():
            print(f"\n{'='*40}")
            print(f"📋 {key}:")
            print(f"{'='*40}")
            print(val[:2000] if isinstance(val, str) else str(val)[:2000])
    else:
        # Run via the full agent (sequential, but with ConcurrentToolExecutor)
        print("🤖 Running via research agent...")
        agent = create_research_agent(model_provider=provider)
        result = agent(f"Research this topic for a YouTube video: {topic}")
        elapsed = time.time() - t0
        print(f"\n⏱️  Agent research completed in {elapsed:.1f}s")
        print(f"\n{'='*40}")
        print(f"📋 Result:")
        print(f"{'='*40}")
        print(str(result)[:3000])


if __name__ == "__main__":
    main()
