"""Stage 7: Quality Rating (Dual-Model Evaluation)."""

from typing import List
import asyncio
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel as OpenAIChatModel
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.anthropic import AnthropicProvider

from backend.config import settings, PipelineConfig
from backend.models import Document, EvaluationResult, EvaluationOutput
from backend.observability import instrument_stage, calculate_openai_cost, calculate_anthropic_cost
import logfire


EVALUATION_INSTRUCTIONS = """You are a quality evaluator for technical documentation answers.

Evaluate the answer on the following criteria and return a structured JSON assessment.

CRITICAL: If the answer essentially says "I don't know", "I can't answer", or "information not available",
it should receive very low scores (0-20) across all criteria, regardless of how politely it's written.

Scoring criteria:
- technical_accuracy (0-100, weight 30%): Is the information correct and up-to-date?
  Score 0-20 if answer says it lacks information.
- clarity (0-100, weight 25%): Is the answer well-structured and easy to understand?
  Score 0-20 if answer doesn't actually provide substantive information.
- completeness (0-100, weight 25%): Does it fully address the question with specific details?
  Score 0-10 if answer admits it cannot answer.
- developer_value (0-100, weight 20%): Is it actionable and useful for developers?
  Score 0-10 if answer just redirects to external resources.
- overall (0-100): Weighted average of the above scores.
- feedback: 1-2 sentences of constructive feedback."""

_openai_eval_agent = Agent(
    OpenAIChatModel(settings.eval_model_openai, provider=OpenAIProvider(api_key=settings.openai_api_key)),
    output_type=EvaluationOutput,
    instructions=EVALUATION_INSTRUCTIONS,
)

_anthropic_eval_agent = Agent(
    AnthropicModel(settings.eval_model_anthropic, provider=AnthropicProvider(api_key=settings.anthropic_api_key)),
    output_type=EvaluationOutput,
    instructions=EVALUATION_INSTRUCTIONS,
)


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

    usage = result.usage()
    input_tokens = usage.request_tokens or 0
    output_tokens = usage.response_tokens or 0
    cost_usd = calculate_openai_cost(input_tokens, output_tokens, settings.eval_model_openai)

    return {
        "output": result.output,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
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

    usage = result.usage()
    input_tokens = usage.request_tokens or 0
    output_tokens = usage.response_tokens or 0
    cost_usd = calculate_anthropic_cost(input_tokens, output_tokens, settings.eval_model_anthropic)

    return {
        "output": result.output,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
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


@instrument_stage(PipelineConfig.STAGE_EVALUATION)
async def evaluate_quality(
    question: str,
    answer: str,
    documents: List[Document]
) -> dict:
    """
    Independent quality assessment from two models.

    Args:
        question: The user's question
        answer: The generated answer
        documents: Source documents

    Returns:
        dict with 'evaluations', 'average_score', 'agreement_level', 'total_cost_usd'
    """

    logfire.info("Evaluating quality with dual models")

    doc_count = len(documents)

    # Run both evaluations in parallel
    openai_result, anthropic_result = await asyncio.gather(
        evaluate_with_openai(question, answer, doc_count),
        evaluate_with_anthropic(question, answer, doc_count),
    )

    openai_eval = build_evaluation_result(openai_result["output"], openai_result["model"])
    anthropic_eval = build_evaluation_result(anthropic_result["output"], anthropic_result["model"])

    evaluations = [openai_eval, anthropic_eval]

    average_score = (openai_eval.score + anthropic_eval.score) / 2
    score_difference = abs(openai_eval.score - anthropic_eval.score)

    if score_difference <= 5:
        agreement_level = "high"
    elif score_difference <= 15:
        agreement_level = "medium"
    else:
        agreement_level = "low"

    total_cost = openai_result["cost_usd"] + anthropic_result["cost_usd"]

    logfire.info(
        "Quality evaluated",
        openai_score=openai_eval.score,
        anthropic_score=anthropic_eval.score,
        average_score=average_score,
        agreement_level=agreement_level,
        score_difference=score_difference,
        cost_usd=total_cost,
    )

    return {
        "evaluations": evaluations,
        "average_score": average_score,
        "agreement_level": agreement_level,
        "cost_usd": total_cost,
    }
