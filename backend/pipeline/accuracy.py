"""Stage 6: Technical Accuracy Check."""

from typing import List
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from backend.config import settings, PipelineConfig
from backend.models import Claim, AccuracyOutput
from backend.observability import instrument_stage, calculate_anthropic_cost
import logfire


ACCURACY_CHECK_INSTRUCTIONS = """You are a technical accuracy reviewer for Render documentation.

Evaluate the technical accuracy of an answer against verified claims and return a structured assessment.

Evaluation Criteria:
- If most claims are verified (70%+), the answer is likely accurate (accuracy_score 90-100)
- CRITICAL: If the answer contains invented information (plan names, features, prices NOT in documentation), score 0-30
- Check for conflation errors (e.g., mixing workspace plans with database plans) - score 20-40 if found
- Verified claims with high similarity scores indicate strong documentation support
- Only penalize for actual technical errors or misleading information
- Minor omissions or lack of detail should not heavily penalize the score

RED FLAGS to check for:
- Invented plan names or tiers not verified by documentation
- Tables or specifications not found in source documents
- Conflating different product types:
  * CRITICAL: Treating "Hobby" or "Professional" as DATABASE plans (they're workspace plans!)
  * Database instance types are: Free, Basic-Xgb, Pro-Xgb, Accelerated-Xgb
  * Workspace plans are: Hobby, Professional (affect PITR retention, team features)
- Making up features, limits, or pricing details

Return a JSON object with:
- accuracy_score (0-100, where 100 is perfectly accurate)
- errors (list of technical errors or inaccuracies found, empty list if none)
- corrections (list of suggested corrections, empty list if none)"""

_accuracy_agent = Agent(
    AnthropicModel(settings.accuracy_model, provider=AnthropicProvider(api_key=settings.anthropic_api_key)),
    output_type=AccuracyOutput,
    instructions=ACCURACY_CHECK_INSTRUCTIONS,
)


@instrument_stage(PipelineConfig.STAGE_ACCURACY)
async def check_accuracy(
    answer: str,
    verified_claims: List[Claim]
) -> dict:
    """
    Deep accuracy validation using Claude.

    Args:
        answer: The generated answer
        verified_claims: Claims with verification results

    Returns:
        dict with 'accuracy_score', 'errors', 'corrections', 'input_tokens', 'output_tokens', 'cost_usd'
    """

    logfire.info("Checking technical accuracy")

    # Prepare claims summary
    claims_text = "\n".join([
        f"- {claim.claim} (verified: {claim.verified}, score: {claim.verification_score:.2f})"
        for claim in verified_claims
    ])

    verified_count = sum(1 for c in verified_claims if c.verified)
    verification_text = f"{verified_count}/{len(verified_claims)} claims verified"

    user_prompt = f"""Original Answer:
{answer}

Extracted Claims:
{claims_text}

Verification Results:
{verification_text}

Evaluate the technical accuracy of this answer."""

    result = await _accuracy_agent.run(
        user_prompt,
        model_settings={"temperature": 0.0, "max_tokens": 1500},
    )

    usage = result.usage()
    input_tokens = usage.request_tokens or 0
    output_tokens = usage.response_tokens or 0
    cost_usd = calculate_anthropic_cost(input_tokens, output_tokens, settings.accuracy_model)

    output = result.output
    accuracy_score = output.accuracy_score
    errors = output.errors
    corrections = output.corrections

    # If high verification rate but low accuracy score with no errors, boost it
    verification_rate = verified_count / len(verified_claims) if verified_claims else 0
    if verification_rate >= 0.7 and accuracy_score < 85 and len(errors) == 0:
        logfire.info(
            f"Boosting accuracy score from {accuracy_score} to 90 due to high verification rate "
            f"({verification_rate:.1%}) and no errors"
        )
        accuracy_score = 90

    logfire.info(
        "Accuracy checked",
        accuracy_score=accuracy_score,
        error_count=len(errors),
        correction_count=len(corrections),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd
    )

    return {
        "accuracy_score": accuracy_score,
        "errors": errors,
        "corrections": corrections,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd
    }
