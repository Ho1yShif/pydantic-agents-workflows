"""Stage 4: Claims Extraction."""

from typing import List
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel as OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import settings, PipelineConfig
from backend.models import ClaimsOutput
from backend.observability import instrument_stage, calculate_openai_cost
import logfire


CLAIMS_EXTRACTION_INSTRUCTIONS = """Extract the verifiable factual claims from answers about Render's platform.

A factual claim is a specific statement about Render's own platform — its features, products, pricing, \
limits, or documented behavior — that could be checked against Render's documentation.

Each extracted claim must be:
- A single, specific, atomic fact (one sentence)
- About Render's platform specifically (not general software/computer-science principles)
- Independently checkable against documentation

DO NOT extract (these are not Render-documentation facts and will always fail verification):
- Rhetorical, motivational, or comparative framing (e.g. "naive parallel calls have no durability", \
"a crash loses everything", "hand-rolled queues require building consumer groups and retry logic")
- General computer-science or industry assertions not specific to Render
- Meta-statements about the answer, the tutorial, or the documentation itself \
(e.g. "the tutorial builds a code-review agent", "the canonical tutorial is located at <url>")
- Opinions, recommendations phrased as preference, or vague generalities

When in doubt, prefer fewer, higher-quality claims that are concrete Render facts.

Return a JSON object with a "claims" array of claim strings."""


_claims_agent = Agent(
    OpenAIChatModel(settings.claims_model, provider=OpenAIProvider(api_key=settings.openai_api_key)),
    output_type=ClaimsOutput,
    instructions=CLAIMS_EXTRACTION_INSTRUCTIONS,
)


@instrument_stage(PipelineConfig.STAGE_CLAIMS)
async def extract_claims(answer: str) -> dict:
    """
    Extract verifiable factual claims from generated answer.

    Args:
        answer: The generated answer text

    Returns:
        dict with 'claims', 'input_tokens', 'output_tokens', 'cost_usd'
    """

    logfire.info(
        "Extracting claims from answer",
        answer_length=len(answer),
        model=settings.claims_model
    )

    result = await _claims_agent.run(
        f"Extract all factual claims from this answer:\n\n{answer}",
        model_settings={"temperature": 0.1, "max_tokens": 4000},
    )

    usage = result.usage()
    input_tokens = usage.request_tokens or 0
    output_tokens = usage.response_tokens or 0
    cost_usd = calculate_openai_cost(input_tokens, output_tokens, settings.claims_model)

    # Warn if response was near the token limit (possible truncation)
    if output_tokens >= 3900:
        logfire.warn(
            "Claims extraction near max_tokens limit - possible truncation",
            max_tokens=4000,
            output_tokens=output_tokens,
            answer_length=len(answer),
        )

    claims: List[str] = result.output.claims

    if len(claims) == 0 and len(answer) > 100:
        logfire.warn(
            "Zero claims extracted from substantial answer",
            claim_count=0,
            answer_length=len(answer),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
    else:
        logfire.info(
            "Claims extracted successfully",
            claim_count=len(claims),
            answer_length=len(answer),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    return {
        "claims": claims,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd
    }
