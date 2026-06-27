"""Shared constructors for the pipeline's pydantic-ai agents.

Every stage builds its ``Agent`` the same way — wrap a provider-specific model
with the API key from ``settings``, an optional typed ``output_type``, and the
stage instructions. These two helpers remove that repeated boilerplate while
keeping each stage's "this stage is an Agent with a typed output" shape obvious.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import settings


def anthropic_agent(model: str, instructions: str, output_type: Any = str) -> Agent:
    """Build a Claude-backed ``Agent`` using the configured Anthropic API key."""
    return Agent(
        AnthropicModel(model, provider=AnthropicProvider(api_key=settings.anthropic_api_key)),
        output_type=output_type,
        instructions=instructions,
    )


def openai_agent(model: str, instructions: str, output_type: Any = str) -> Agent:
    """Build a GPT-backed ``Agent`` using the configured OpenAI API key."""
    return Agent(
        OpenAIChatModel(model, provider=OpenAIProvider(api_key=settings.openai_api_key)),
        output_type=output_type,
        instructions=instructions,
    )
