"""Quality: developer-experience evaluation (dual-model).

The verification capability that owns *answer quality* — clarity, completeness, and
actionability for the developer who asked. Two independent judges (OpenAI + Anthropic)
score in parallel and their agreement is a confidence signal. Factual grounding is
checked separately by the Accuracy stage, so this stage does not re-verify each fact."""

from backend.config import settings
from backend.models import EvaluationResult, EvaluationOutput
from backend.observability import (
    calculate_openai_cost,
    calculate_anthropic_cost,
    usage_and_cost,
)
from backend.pipeline._agents import anthropic_agent, openai_agent


EVALUATION_INSTRUCTIONS = """You are a quality evaluator for technical documentation answers.

Judge how well the answer SERVES THE DEVELOPER who asked the question — its clarity, structure,
completeness of coverage, and actionability. Factual verification against the source documentation
is handled by a separate accuracy stage, so focus on the quality and usefulness of the response
rather than re-checking each fact. Return a structured JSON assessment.

CRITICAL: If the answer essentially says "I don't know", "I can't answer", or "information not available",
it should receive very low scores (0-20) across all criteria, regardless of how politely it's written.

Scoring criteria:
- technical_accuracy (0-100, weight 30%): Is the answer technically sound and internally consistent —
  free of obviously contradictory or misleading statements? Score 0-20 if answer says it lacks information.
- clarity (0-100, weight 25%): Is the answer well-structured and easy to understand?
  Score 0-20 if answer doesn't actually provide substantive information.
- completeness (0-100, weight 25%): Does it fully address the question with specific details?
  Score 0-10 if answer admits it cannot answer.
- developer_value (0-100, weight 20%): Is it actionable and useful for developers?
  Score 0-10 if answer just redirects to external resources.
- overall (0-100): Weighted average of the above scores.
- feedback: 1-2 sentences of constructive feedback."""

_openai_eval_agent = openai_agent(
    settings.eval_model_openai, EVALUATION_INSTRUCTIONS, output_type=EvaluationOutput
)

_anthropic_eval_agent = anthropic_agent(
    settings.eval_model_anthropic, EVALUATION_INSTRUCTIONS, output_type=EvaluationOutput
)


def agreement_level(score_difference: float) -> str:
    """Map the gap between the two judges' scores to a qualitative agreement label."""
    if score_difference <= 5:
        return "high"
    if score_difference <= 15:
        return "medium"
    return "low"


async def evaluate_with_openai(question: str, answer: str, doc_count: int) -> dict:
    """Evaluate with OpenAI GPT-4o."""

    user_prompt = f"""Question: {question}

Answer:
{answer}

Source Documents Used: {doc_count}

Evaluate the quality of this answer."""

    result = await _openai_eval_agent.run(
        user_prompt,
        model_settings={"temperature": 0.1, "max_tokens": 500},
    )

    usage = usage_and_cost(result, calculate_openai_cost, settings.eval_model_openai)

    return {
        "output": result.output,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cost_usd": usage["cost_usd"],
        "model": settings.eval_model_openai,
    }


async def evaluate_with_anthropic(question: str, answer: str, doc_count: int) -> dict:
    """Evaluate with Anthropic Claude."""

    user_prompt = f"""Question: {question}

Answer:
{answer}

Source Documents Used: {doc_count}

Evaluate the quality of this answer."""

    result = await _anthropic_eval_agent.run(
        user_prompt,
        model_settings={"temperature": 0.1, "max_tokens": 500},
    )

    usage = usage_and_cost(result, calculate_anthropic_cost, settings.eval_model_anthropic)

    return {
        "output": result.output,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cost_usd": usage["cost_usd"],
        "model": settings.eval_model_anthropic,
    }


def build_evaluation_result(output: EvaluationOutput, model: str) -> EvaluationResult:
    """Build an EvaluationResult from structured agent output."""
    return EvaluationResult(
        model=model,
        score=output.overall,
        technical_accuracy=output.technical_accuracy,
        clarity=output.clarity,
        completeness=output.completeness,
        developer_value=output.developer_value,
        feedback=output.feedback,
    )
