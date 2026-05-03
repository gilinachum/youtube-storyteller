"""StoryTeller — AI-powered YouTube video planning agent.

Main entrypoint for the Strands agent.
"""

import sys
import os
import logging

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
from agent.tools.save_user_photo import make_save_user_photo_tool
from agent.research_agent import create_research_agent
from agent.thumbnail_agent import create_thumbnail_agent

logger = logging.getLogger(__name__)


def email_to_actor_id(email: str) -> str:
    """Convert email to valid AgentCore actorId.

    AgentCore pattern: [a-zA-Z0-9][a-zA-Z0-9-_/]*
    'gili@amazon.com' → 'gili-at-amazon-com'
    'gili+oc3@amazon.com' → 'gili-oc3-at-amazon-com'
    """
    return email.replace("@", "-at-").replace("+", "-").replace(".", "-")


def create_agent(email: str = "", session_id: str = "") -> Agent:
    """Create and configure the StoryTeller agent."""

    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-6",
        region_name=os.environ.get("AWS_REGION", "us-west-2"),
        max_tokens=8192,
    )

    system_prompt = build_system_prompt()

    # Create session-aware tools
    name_session = make_name_session_tool(email, session_id)
    export_document = make_export_document_tool(email, session_id)
    save_user_photo = make_save_user_photo_tool(email)

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

    # Create thumbnail sub-agent as a tool (preserve_context for iterative design)
    thumbnail_agent = create_thumbnail_agent(email=email)
    thumbnail_tool = thumbnail_agent.as_tool(
        name="design_thumbnail",
        description=(
            "Design and generate YouTube thumbnail images. Pass a description of "
            "the video topic and any design preferences. The thumbnail designer "
            "maintains context across calls — use it for iterative refinement "
            "(e.g., 'make text bigger', 'change colors', 'try a different style'). "
            "It can also list available style templates and the user's profile photos."
        ),
        preserve_context=True,
    )

    # Session manager — AgentCore Memory handles message persistence
    session_manager = None
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if email and session_id and memory_id:
        try:
            from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
            from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

            config = AgentCoreMemoryConfig(
                memory_id=memory_id,
                session_id=session_id,
                actor_id=email_to_actor_id(email),
            )
            session_manager = AgentCoreMemorySessionManager(
                agentcore_memory_config=config,
                region_name=os.environ.get("AWS_REGION", "us-west-2"),
            )
            logger.info("AgentCore Memory session manager initialized (memory=%s, session=%s)", memory_id, session_id)
        except Exception as e:
            logger.warning("Failed to initialize AgentCore Memory session manager: %s", e)
            session_manager = None

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[
            pdf_extract,
            pptx_extract,
            name_session,
            export_document,
            save_user_photo,
            research_tool,
            thumbnail_tool,
        ],
        session_manager=session_manager,
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
