"""Query expansion for improved retrieval diversity and coverage."""

from typing import List
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel as OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import settings
from backend.models import QueryExpansionOutput
from backend.observability import calculate_openai_cost
import logfire


QUERY_EXPANSION_INSTRUCTIONS = """You are a search query expert for Render's cloud platform documentation.

Given a user's question, generate 2-3 alternative phrasings that would help retrieve comprehensive documentation from different angles.

Guidelines:
1. **Product Coverage**: If the question is about a general category (e.g., "databases"), explicitly mention ALL relevant products:
   - Databases → Mention both "Postgres" AND "Key Value"
   - Services → Mention "web services", "workers", "cron jobs"
   - Storage → Mention "Postgres storage", "disk storage", "persistent volumes"

2. **Terminology Variations**: Use synonyms and alternative terms:
   - database/datastore
   - plan/tier/instance type
   - pricing/cost/billing
   - backup/recovery/restore

3. **Different Aspects**: Approach from different angles:
   - Features/capabilities
   - Configuration/setup
   - Pricing/plans
   - Limitations/restrictions

4. **Specificity Balance**: Mix general and specific queries:
   - One broad query (covers category)
   - One or two specific queries (target specific products)

Return a JSON object with a "queries" array containing 2-3 alternative phrasings (do NOT include the original question).

Example:
Input: "What database plans does Render offer?"
Output: {"queries": ["What are the Postgres instance types and pricing?", "What Key Value datastore plans does Render provide?"]}
"""

_query_expansion_agent = Agent(
    OpenAIChatModel(settings.query_expansion_model, provider=OpenAIProvider(api_key=settings.openai_api_key)),
    output_type=QueryExpansionOutput,
    instructions=QUERY_EXPANSION_INSTRUCTIONS,
)


async def expand_query(question: str) -> tuple[List[str], float]:
    """
    Use LLM to generate query variations for better retrieval coverage.

    Args:
        question: Original user question

    Returns:
        Tuple of (list of query variations, cost in USD)
    """

    logfire.info("Expanding query with LLM", original_question=question)

    result = await _query_expansion_agent.run(
        f"Original question: {question}",
        model_settings={"temperature": 0.3, "max_tokens": 300},
    )

    usage = result.usage()
    cost_usd = calculate_openai_cost(
        usage.request_tokens or 0,
        usage.response_tokens or 0,
        settings.query_expansion_model,
    )

    # Limit to 2 expanded queries, then prepend original to ensure it's always included
    variations = [question] + result.output.queries[:2]

    logfire.info(
        "Query expanded successfully",
        num_variations=len(variations),
        variations=variations,
        cost_usd=cost_usd,
    )

    return variations, cost_usd


async def should_expand_query(question: str) -> bool:
    """
    Determine if a question would benefit from query expansion.

    Some questions are specific enough that expansion isn't needed.
    Others are broad/ambiguous and benefit from multiple perspectives.

    Args:
        question: User's question

    Returns:
        True if query expansion would help
    """

    question_lower = question.lower()

    # Broad category questions that need expansion
    broad_terms = [
        "database", "plan", "tier", "option", "service",
        "storage", "backup", "monitoring", "scaling",
        "pricing", "cost", "feature", "capability"
    ]

    # Very specific questions that don't need expansion
    specific_indicators = [
        "how do i", "how to", "error", "troubleshoot",
        "specific", "exactly", "step by step"
    ]

    # Check for broad terms
    has_broad_term = any(term in question_lower for term in broad_terms)

    # Check for specific indicators
    is_specific = any(indicator in question_lower for indicator in specific_indicators)

    # Check length (very long questions are usually specific)
    is_detailed = len(question.split()) > 15

    # Expand if broad AND not specific
    should_expand = has_broad_term and not (is_specific or is_detailed)

    logfire.debug(
        "Query expansion decision",
        question=question,
        should_expand=should_expand,
        has_broad_term=has_broad_term,
        is_specific=is_specific,
        is_detailed=is_detailed,
    )

    return should_expand
