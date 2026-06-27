"""Stage 3: Answer Generation."""

from typing import List, Optional

from backend.config import settings, PipelineConfig
from backend.models import Document
from backend.observability import instrument_stage, calculate_anthropic_cost, usage_and_cost
from backend.pipeline._agents import anthropic_agent
import logfire


ANSWER_GENERATION_INSTRUCTIONS = """You are a technical assistant for Render's cloud platform. Answer developer questions accurately and clearly, using only the documentation provided in the prompt.

Grounding rules:
- Use only information present in the provided context. Do not invent, assume, or extrapolate — every specific plan name, tier, feature, limit, or price you state must appear in the context.
- When the context contains the answer, state it directly. Don't hedge with phrases like "the documentation doesn't specify" if the information is actually present; check the provided documents before concluding something is missing.
- If the information is genuinely absent from the context, say so plainly rather than guessing.
- Keep distinct product types separate. Workspace plans (e.g. Hobby, Professional) are not the same as database/datastore instance types (e.g. Free, Basic, Pro). A "database" or "datastore" question covers both Postgres and Key Value; only attribute a feature to a product when the context shows that product supports it.
- Don't fabricate tables, lists, or specifications — only structure information that is explicitly in the context."""

_answer_agent = anthropic_agent(settings.answer_model, ANSWER_GENERATION_INSTRUCTIONS)


@instrument_stage(PipelineConfig.STAGE_GENERATION)
async def generate_answer(
    question: str,
    documents: List[Document],
    feedback: Optional[str] = None
) -> dict:
    """
    Generate comprehensive answer using retrieved context.

    Args:
        question: The user's question
        documents: Retrieved documentation chunks
        feedback: Optional feedback from previous iteration

    Returns:
        dict with 'answer', 'input_tokens', 'output_tokens', 'cost_usd'
    """

    logfire.info(
        "Generating answer with Claude",
        num_documents=len(documents),
        question_length=len(question),
        has_feedback=feedback is not None,
        model=settings.answer_model
    )

    # Prepare context from documents
    context_parts = []
    for i, doc in enumerate(documents, 1):
        doc_metadata = doc.metadata or {}
        title = doc_metadata.get('title', 'Unknown')
        context_parts.append(
            f"[Document {i}] {title}\n"
            f"Source: {doc.source}\n"
            f"Content: {doc.content}\n"
        )

    context = "\n\n".join(context_parts)

    # Build the user prompt
    feedback_text = ""
    if feedback:
        feedback_text = f"""
Feedback from quality check:
{feedback}

When revising, only add details that are explicitly in the provided documents.
Keep product-specific features separate (e.g. label "Postgres:" vs "Key Value:")
and do not generalize "both support X" unless both products show it in the context.
When in doubt, be less comprehensive but more accurate."""

    user_prompt = f"""Context from Render documentation:
{context}

User Question: {question}
{feedback_text}

Please provide a comprehensive answer that:
1. Uses only information from the provided context
2. States facts confidently when they appear in the documentation (no unnecessary hedging)
3. Lists specific plans, tiers, features, and limits found in the context
4. Only says "not specified" if genuinely absent from the documents provided above

Answer:"""

    result = await _answer_agent.run(
        user_prompt,
        model_settings={"temperature": 0.3, "max_tokens": settings.max_tokens},
    )

    usage = usage_and_cost(result, calculate_anthropic_cost, settings.answer_model)
    input_tokens, output_tokens, cost_usd = (
        usage["input_tokens"], usage["output_tokens"], usage["cost_usd"]
    )

    logfire.info(
        "Answer generated",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        answer_length=len(result.output)
    )

    return {
        "answer": result.output,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd
    }
