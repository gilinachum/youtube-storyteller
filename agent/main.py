"""StoryTeller — AI-powered YouTube video planning agent.

Main entrypoint for the Strands agent.
"""

import sys
import os

# Add the project root to path so agent package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from strands.models import BedrockModel

from agent.system_prompt import build_system_prompt
from agent.tools import (
    content_fetch,
    pdf_extract,
    pptx_extract,
    web_research,
    trend_analysis,
)
from agent.tools.session_manager import make_name_session_tool
from agent.tools.export_document import make_export_document_tool
from agent.research_agent import create_research_agent


def create_agent(email: str = "", session_id: str = "") -> Agent:
    """Create and configure the StoryTeller agent."""

    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-6",
        region_name="us-east-1",
        max_tokens=8192,
    )

    system_prompt = build_system_prompt()

    # Create session-aware tools
    name_session = make_name_session_tool(email, session_id)
    export_document = make_export_document_tool(email, session_id)

    # Create research sub-agent as a tool
    research_agent = create_research_agent()
    research_tool = research_agent.as_tool(
        name="deep_research",
        description=(
            "Run comprehensive research on a topic for video planning. "
            "This tool coordinates web search, trend analysis, and URL scraping "
            "to produce a structured research brief. Use this instead of calling "
            "web_research/trend_analysis/content_fetch individually — it's faster "
            "and more thorough. Pass a clear research request describing what to find."
        ),
    )

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[
            pdf_extract,
            pptx_extract,
            name_session,
            export_document,
            research_tool,
        ],
    )

    return agent


def main():
    """Run the agent in CLI test mode."""
    agent = create_agent()

    if len(sys.argv) > 1:
        # Run with a specific prompt from command line
        prompt = " ".join(sys.argv[1:])
    else:
        # Default test prompt
        prompt = "I want to make a video about Amazon Bedrock AgentCore Memory"

    print(f"\n{'='*60}")
    print(f"StoryTeller Agent — Test Mode")
    print(f"Prompt: {prompt}")
    print(f"{'='*60}\n")

    response = agent(prompt)
    print(f"\n{'='*60}")
    print("Agent response complete.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
