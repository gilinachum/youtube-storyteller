"""Model-specific configuration for StoryTeller agent.

Registry-based approach: each model gets its own config entry.
Add new models by adding entries to MODEL_REGISTRY.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union


@dataclass
class ModelConfig:
    """Configuration bundle for a specific model."""

    provider: str  # "bedrock" or "openai-compatible"
    model_id: str
    region: str = ""

    # Tool choice: "auto", "required", or a dict for specific tool forcing
    tool_choice: str = "auto"

    # Max output tokens
    max_tokens: int = 8192

    # System prompt preamble (prepended to the standard prompt)
    system_preamble: str = ""

    # Extra model params (temperature, top_p, etc.)
    extra_params: dict = field(default_factory=dict)

    # Auth: secret name in Secrets Manager (for API-key-based providers)
    # If None, uses IAM/SigV4 (default Bedrock behavior)
    api_key_secret: Optional[str] = None

    # Base URL override (for non-Bedrock providers)
    base_url: Optional[str] = None


# ── Model Registry ───────────────────────────────────────────────────────────
# Add new models here. Key = provider name used in AGENT_MODEL_PROVIDER env var.
# Each entry is a callable that returns a ModelConfig.

def _bedrock_config() -> ModelConfig:
    """Standard Bedrock Converse API (Sonnet, Nova, Llama, etc.)."""
    return ModelConfig(
        provider="bedrock",
        model_id=os.environ.get("AGENT_MODEL_ID", "global.anthropic.claude-sonnet-5"),
        region=os.environ.get("AWS_REGION", "us-west-2"),
    )


def _mantle_config() -> ModelConfig:
    """Bedrock Mantle (OpenAI-compatible endpoint for marketplace models)."""
    region = os.environ.get("MANTLE_REGION", os.environ.get("AWS_REGION", "us-west-2"))
    model_id = os.environ.get("AGENT_MODEL_ID", "xai.grok-4.3")
    return ModelConfig(
        provider="openai-compatible",
        model_id=model_id,
        region=region,
        api_key_secret="bedrock/mantle-api-key",
        base_url=f"https://bedrock-mantle.{region}.api.aws/openai/v1",
    )


MODEL_REGISTRY: dict[str, Callable[[], ModelConfig]] = {
    "bedrock": _bedrock_config,
    "mantle": _mantle_config,
    # Add future providers here:
    # "openrouter": _openrouter_config,
    # "anthropic-direct": _anthropic_direct_config,
}


def get_model_config() -> ModelConfig:
    """Build ModelConfig from environment variables.

    Uses AGENT_MODEL_PROVIDER to select from MODEL_REGISTRY.
    Defaults to "bedrock" if not set or unrecognized.
    """
    provider_key = os.environ.get("AGENT_MODEL_PROVIDER", "bedrock").lower()

    factory = MODEL_REGISTRY.get(provider_key, _bedrock_config)
    return factory()
