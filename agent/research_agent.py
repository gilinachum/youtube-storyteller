"""Research sub-agent for StoryTeller.

Runs web research, trend analysis, and content fetching in parallel
via a dedicated Strands agent with its own system prompt.
The parent agent calls this as a single tool — the sub-agent coordinates
multiple research tasks internally.
"""

from strands import Agent
from strands.models import BedrockModel

from agent.tools import (
    content_fetch,
    web_research,
    trend_analysis,
)


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


def create_research_agent() -> Agent:
    """Create a research sub-agent with web tools."""

    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-6",
        region_name=os.environ.get("AWS_REGION", "us-west-2"),
        max_tokens=8192,
    )

    return Agent(
        name="research_assistant",
        description=(
            "Research a topic thoroughly for YouTube video planning. "
            "Gathers web research, trend analysis, and URL content. "
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
    )
