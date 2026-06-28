"""In-process Q&A pipeline orchestrator.

Runs the full Q&A pipeline inside the FastAPI process — no Render Workflows.
``POST /ask`` launches ``run_qa_pipeline`` as a background task; it drives the
data-dependent stages directly (the I/O-bound calls overlap for free) and fans
the two heaviest review stages out with ``asyncio.gather``. Live per-stage
progress is persisted under ``progress_token`` so the poll endpoint can surface
stage-by-stage feedback to the UI.
"""

from __future__ import annotations

import asyncio
import time

import logfire

from backend.config import settings
from backend.database import vector_store
from backend.models import AnswerResponse, PipelineStageResult
from backend.observability import pipeline_trace, track_pipeline_metrics
from backend.pipeline import (
    check_accuracy,
    collapse_sources,
    embed_question,
    extract_claims,
    generate_answer,
    retrieve_documents,
    verify_claims,
)
from backend.pipeline.evaluation import (
    agreement_level,
    build_evaluation_result,
    evaluate_with_anthropic,
    evaluate_with_openai,
)


def _stage_result(
    stage: str,
    *,
    cost_usd: float,
    duration_ms: float = 0.0,
    tokens_used: int | None = None,
    model: str | None = None,
    metadata: dict | None = None,
) -> PipelineStageResult:
    """Build a successful ``PipelineStageResult`` for the observability trail."""
    return PipelineStageResult(
        stage=stage,
        success=True,
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        tokens_used=tokens_used,
        model=model,
        metadata=dict(metadata or {}),
    )


async def run_qa_pipeline(
    question: str,
    session_id: str | None = None,
    client_id: str | None = None,
    progress_token: str | None = None,
) -> AnswerResponse:
    """Orchestrate the Q&A pipeline in-process and return the ``AnswerResponse``.

    Retrieval (embedding + RAG) runs first, then the answer is generated and put
    through three verification capabilities: claim grounding (extract → verify),
    technical-accuracy review, and a dual-model quality rating. Accuracy and the
    two quality judges have no mutual dependency, so they run concurrently.
    """

    async with pipeline_trace(question):
        stages: list[PipelineStageResult] = []
        total_cost = 0.0
        pipeline_start = time.time()

        # Live per-stage feedback. Each stage appends to a cumulative list persisted
        # under `progress_token`; the gateway reads it on every poll so the UI advances
        # stage-by-stage in real time. No-ops when no token is supplied.
        progress: list[dict] = []

        async def emit(stage: str, status: str, message: str, pct: float, cost: float) -> None:
            if not progress_token:
                return
            progress.append({
                "stage": stage,
                "status": status,
                "message": message,
                "progress": round(min(pct, 100.0), 1),
                "cost_so_far": round(cost, 4),
            })
            try:
                await vector_store.record_progress(progress_token, progress)
            except Exception as e:  # noqa: BLE001 - progress is best-effort
                logfire.warning(f"Failed to record progress: {e}")

        # --- Retrieval phase: embedding + RAG ---
        await emit("question_embedding", "started", "Embedding your question...", 5, total_cost)
        embed_result = await embed_question(question)
        stages.append(_stage_result(
            "question_embedding",
            cost_usd=embed_result["cost_usd"],
            tokens_used=embed_result["tokens"],
            model=settings.embedding_model,
            metadata={"embedding_dimensions": len(embed_result["embedding"])},
        ))
        total_cost += embed_result["cost_usd"]
        await emit("question_embedding", "completed", "Question embedded", 12.5, total_cost)

        await emit("rag_retrieval", "started", "Searching documentation...", 15, total_cost)
        retrieval_result = await retrieve_documents(
            embed_result["embedding"], original_question=question
        )
        stages.append(_stage_result(
            "rag_retrieval",
            cost_usd=retrieval_result["cost_usd"],
            model=settings.query_expansion_model,
            metadata={
                "documents_retrieved": len(retrieval_result["documents"]),
                "queries_expanded": retrieval_result.get("queries_count", 1),
            },
        ))
        total_cost += retrieval_result["cost_usd"]
        documents = retrieval_result["documents"]
        await emit(
            "rag_retrieval", "completed",
            f"Found {len(documents)} relevant documents", 25, total_cost,
        )

        # --- Generate phase: the expensive Claude call ---
        await emit("generation", "started", "Generating answer...", 28, total_cost)
        gen_result = await generate_answer(question, documents)
        stages.append(_stage_result(
            "answer_generation",
            cost_usd=gen_result["cost_usd"],
            tokens_used=gen_result["input_tokens"] + gen_result["output_tokens"],
            model=settings.answer_model,
            metadata={"answer_length": len(gen_result["answer"])},
        ))
        total_cost += gen_result["cost_usd"]
        answer_text = gen_result["answer"]
        await emit("generation", "completed", "Answer generated", 37, total_cost)

        # --- Grounding phase: extract claims, then verify them against sources ---
        await emit("claims", "started", "Extracting factual claims...", 43, total_cost)
        claims_result = await extract_claims(answer_text)
        stages.append(_stage_result(
            "claims_extraction",
            cost_usd=claims_result["cost_usd"],
            tokens_used=claims_result["input_tokens"] + claims_result["output_tokens"],
            model=settings.claims_model,
            metadata={"claims_extracted": len(claims_result["claims"])},
        ))
        total_cost += claims_result["cost_usd"]
        await emit(
            "claims", "completed",
            f"Extracted {len(claims_result['claims'])} claims", 49, total_cost,
        )

        await emit("verification", "started", "Verifying claims...", 55, total_cost)
        verification_result = await verify_claims(claims_result["claims"])
        verified_claims = verification_result["verified_claims"]
        verification_rate = verification_result["verification_rate"] * 100
        verified_count = len([c for c in verified_claims if c.verified])
        stages.append(_stage_result(
            "claims_verification",
            cost_usd=verification_result["cost_usd"],
            tokens_used=verification_result["tokens_used"],
            model=settings.embedding_model,
            metadata={
                "claims_verified": verified_count,
                "total_claims": len(verified_claims),
                "verification_rate": f"{verification_rate:.0f}%",
            },
        ))
        total_cost += verification_result["cost_usd"]
        await emit(
            "verification", "completed",
            f"{verification_rate:.0f}% claims verified", 61, total_cost,
        )

        # --- Accuracy + Quality phase: three concurrent reviews ---
        await emit(
            "accuracy", "started",
            "Checking accuracy & quality in parallel...", 67, total_cost,
        )
        stage_start = time.time()
        accuracy_result, openai_raw, anthropic_raw = await asyncio.gather(
            check_accuracy(answer_text, verified_claims),
            evaluate_with_openai(question, answer_text, len(documents)),
            evaluate_with_anthropic(question, answer_text, len(documents)),
        )
        parallel_duration = (time.time() - stage_start) * 1000

        accuracy_score = accuracy_result["accuracy_score"]
        openai_eval = build_evaluation_result(openai_raw["output"], openai_raw["model"])
        anthropic_eval = build_evaluation_result(anthropic_raw["output"], anthropic_raw["model"])
        evaluations = [openai_eval, anthropic_eval]
        average_score = (openai_eval.score + anthropic_eval.score) / 2
        agreement = agreement_level(abs(openai_eval.score - anthropic_eval.score))
        eval_cost = openai_raw["cost_usd"] + anthropic_raw["cost_usd"]
        eval_tokens = (
            openai_raw["input_tokens"] + openai_raw["output_tokens"]
            + anthropic_raw["input_tokens"] + anthropic_raw["output_tokens"]
        )
        stages.append(_stage_result(
            "technical_accuracy",
            duration_ms=parallel_duration,
            cost_usd=accuracy_result["cost_usd"],
            tokens_used=accuracy_result["input_tokens"] + accuracy_result["output_tokens"],
            model=settings.accuracy_model,
            metadata={"accuracy_score": accuracy_score},
        ))
        total_cost += accuracy_result["cost_usd"]
        await emit(
            "accuracy", "completed",
            f"Accuracy score: {accuracy_score}/100", 79, total_cost,
        )
        stages.append(_stage_result(
            "quality_evaluation",
            duration_ms=parallel_duration,
            cost_usd=eval_cost,
            tokens_used=eval_tokens,
            model=f"{settings.eval_model_openai} + {settings.eval_model_anthropic}",
            metadata={
                "quality_score": f"{average_score:.1f}",
                "openai_score": openai_eval.score,
                "claude_score": anthropic_eval.score,
                "agreement": agreement,
            },
        ))
        total_cost += eval_cost
        await emit(
            "evaluation", "completed",
            f"Quality score: {average_score:.1f}/100", 90, total_cost,
        )
        await emit("finalize", "completed", "Answer ready", 95, total_cost)

        total_duration_ms = (time.time() - pipeline_start) * 1000

        response = AnswerResponse(
            question=question,
            answer=answer_text,
            # Generation above saw every chunk; the user-facing sources list collapses
            # chunks of one page into a single entry (see collapse_sources).
            sources=collapse_sources(documents),
            claims=verified_claims,
            quality_score=average_score,
            accuracy_score=accuracy_score,
            evaluations=evaluations,
            total_cost=total_cost,
            total_duration_ms=total_duration_ms,
            stages=stages,
            session_id=session_id,
        )

        response.session_id = await _persist_session(response, client_id)

        track_pipeline_metrics(
            question=question,
            total_cost=total_cost,
            total_duration_ms=total_duration_ms,
            quality_score=average_score,
            accuracy_score=accuracy_score,
            session_id=response.session_id,
        )

        return response


async def _persist_session(response: AnswerResponse, client_id: str | None = None) -> str | None:
    """Save the completed Q&A session to the database (best-effort)."""
    from opentelemetry import trace

    try:
        current_span = trace.get_current_span()
        trace_id = None
        if current_span and current_span.get_span_context().is_valid:
            trace_id = format(current_span.get_span_context().trace_id, "032x")
        saved_id = await vector_store.save_session(
            question=response.question,
            answer=response.answer,
            sources=[doc.model_dump() for doc in response.sources],
            claims=[c.model_dump() for c in response.claims],
            evaluations=[e.model_dump() for e in response.evaluations],
            quality_score=response.quality_score,
            total_cost=response.total_cost,
            total_duration_ms=response.total_duration_ms,
            trace_id=trace_id,
            stages=[s.model_dump() for s in response.stages],
            client_id=client_id,
        )
        logfire.info(f"Saved session to database: {saved_id}", trace_id=trace_id)
        return saved_id
    except Exception as e:  # noqa: BLE001 - persistence is best-effort
        logfire.error(f"Failed to save session: {e}")
        return None
