"""Render Workflows task definitions for the Ask Render Anything Assistant.

This module is the Workflow service entrypoint. Run it with the SDK CLI:

    render-workflows workflows.app:app

Two families of tasks live here, both thin wrappers over existing code:

* **Q&A pipeline** — ``run_qa_pipeline`` is the orchestrator (one run per
  question). It runs the data-dependent stages in-process (cheap I/O-bound
  calls that ``asyncio.gather`` already overlaps for free) and fans out only
  the two heaviest LLM stages — technical accuracy and dual-model evaluation —
  as parallel subtasks, where cross-instance parallelism actually beats the
  per-run spin-up cost.

* **Ingestion** — ``ingest_all`` replaces the old sequential ``preDeployCommand``
  by fanning out the independent document-injection scripts in parallel.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Ensure the repo root is importable so `backend.*` and `data.scripts.*`
# resolve regardless of the working directory the workflow runs from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logfire
from render_sdk import Retry, Workflows

# Importing observability configures Logfire at module load (same as the web app).
from backend.observability import pipeline_trace, track_pipeline_metrics
from backend.config import settings
from backend.database import vector_store
from backend.models import AnswerResponse, EvaluationResult, PipelineStageResult
from backend.prices import load_prices
from backend.pipeline import (
    check_accuracy,
    embed_question,
    extract_claims,
    generate_answer,
    quality_gate_decision,
    retrieve_documents,
    verify_claims,
)
from backend.pipeline.evaluation import (
    build_evaluation_result,
    evaluate_with_anthropic,
    evaluate_with_openai,
)
from workflows.serialization import (
    claims_from_json,
    claims_to_json,
    documents_from_json,
    documents_to_json,
)

app = Workflows(
    default_retry=Retry(max_retries=2, wait_duration_ms=1000, backoff_scaling=2.0),
    default_timeout=300,
    default_plan="standard",
)


async def _ensure_ready(db: bool = False) -> None:
    """Initialize per-instance dependencies a task relies on.

    Each task run is a fresh instance, so model-price data (for cost tracking)
    and — when needed — the pgvector connection pool must be initialized here
    rather than assumed from a long-lived process.
    """
    await load_prices()
    if db:
        await vector_store.initialize()


def _stage_result(
    stage: str,
    *,
    cost_usd: float,
    iteration: int | None = None,
    duration_ms: float = 0.0,
    tokens_used: int | None = None,
    model: str | None = None,
    metadata: dict | None = None,
) -> PipelineStageResult:
    """Build a successful ``PipelineStageResult`` for the observability trail.

    When ``iteration`` is given, it is appended to the stage name as
    ``_iter_{n}`` and folded into ``metadata`` — so the stage-naming convention
    lives here and each call site stays a single line.
    """
    meta = dict(metadata or {})
    if iteration is not None:
        stage = f"{stage}_iter_{iteration}"
        meta["iteration"] = iteration
    return PipelineStageResult(
        stage=stage,
        success=True,
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        tokens_used=tokens_used,
        model=model,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Q&A pipeline — per-stage subtasks
#
# Each post-retrieval LLM stage is its own retried, right-sized task. A
# *transient* failure (provider timeout/rate-limit) then retries that stage in
# isolation instead of failing the orchestrator and re-running the expensive
# generation from the top. All run on `standard` (the default) — the heavy
# compute is on the LLM provider, so the instance just holds an HTTP call + text.
# ---------------------------------------------------------------------------

@app.task(timeout_seconds=120, retry=Retry(max_retries=3, wait_duration_ms=2000, backoff_scaling=2.0))
async def generate_answer_task(question: str, documents_json: list[dict], feedback: str | None = None) -> dict:
    """Subtask: answer generation (Claude). Most expensive + most rate-limit-prone."""
    await _ensure_ready()
    documents = documents_from_json(documents_json)
    return await generate_answer(question, documents, feedback)


@app.task(timeout_seconds=60, retry=Retry(max_retries=2, wait_duration_ms=1000))
async def extract_claims_task(answer: str) -> dict:
    """Subtask: claims extraction (OpenAI). Returns JSON-native claims + cost."""
    await _ensure_ready()
    return await extract_claims(answer)


@app.task(timeout_seconds=90, retry=Retry(max_retries=2, wait_duration_ms=1000))
async def verify_claims_task(claims: list[str]) -> dict:
    """Subtask: claims verification. Keeps its internal per-claim asyncio.gather
    (embedding lookups are ms-scale; per-claim fan-out would be slower/costlier)."""
    await _ensure_ready(db=True)
    result = await verify_claims(claims)
    return {
        "verified_claims": claims_to_json(result["verified_claims"]),
        "verification_rate": result["verification_rate"],
        "cost_usd": result["cost_usd"],
    }


@app.task(timeout_seconds=90, retry=Retry(max_retries=2, wait_duration_ms=1000))
async def check_accuracy_task(answer: str, claims_json: list[dict]) -> dict:
    """Subtask: technical-accuracy check (Claude)."""
    await _ensure_ready()
    verified_claims = claims_from_json(claims_json)
    # Returns plain JSON-serializable dict (scores, errors, corrections, cost).
    return await check_accuracy(answer, verified_claims)


async def _rate_quality(rater, question: str, answer: str, doc_count: int) -> dict:
    """Shared body for the two rater subtasks: run one judge, return its
    EvaluationResult + cost. The raters only use the document *count*."""
    await _ensure_ready()
    result = await rater(question, answer, doc_count)
    evaluation = build_evaluation_result(result["output"], result["model"])
    return {"evaluation": evaluation.model_dump(mode="json"), "cost_usd": result["cost_usd"]}


@app.task(timeout_seconds=60, retry=Retry(max_retries=2, wait_duration_ms=1000))
async def rate_quality_openai_task(question: str, answer: str, doc_count: int) -> dict:
    """Subtask: OpenAI quality judge (runs on its own instance, parallel to Claude judge)."""
    return await _rate_quality(evaluate_with_openai, question, answer, doc_count)


@app.task(timeout_seconds=60, retry=Retry(max_retries=2, wait_duration_ms=1000))
async def rate_quality_anthropic_task(question: str, answer: str, doc_count: int) -> dict:
    """Subtask: Claude quality judge (runs on its own instance, parallel to OpenAI judge)."""
    return await _rate_quality(evaluate_with_anthropic, question, answer, doc_count)


# ---------------------------------------------------------------------------
# Q&A pipeline — orchestrator
# ---------------------------------------------------------------------------

@app.task(timeout_seconds=600)
async def run_qa_pipeline(question: str, session_id: str | None = None) -> dict:
    """Orchestrate the full 8-stage Q&A pipeline as one workflow run.

    Runs embedding and retrieval in-process, then loops generation → claims →
    verification → (accuracy + dual-model evaluation) → quality gate up to
    ``settings.max_iterations`` times, refining with feedback when the gate
    fails. The accuracy and two evaluation stages fan out to parallel subtasks.
    Returns the ``AnswerResponse`` as a JSON-serializable dict.
    """
    await _ensure_ready(db=True)

    async with pipeline_trace(question):
        stages: list[PipelineStageResult] = []
        total_cost = 0.0
        pipeline_start = time.time()

        # Stage 1: Question embedding
        embed_result = await embed_question(question)
        stages.append(_stage_result(
            "question_embedding",
            cost_usd=embed_result["cost_usd"],
            tokens_used=embed_result["tokens"],
            model=settings.embedding_model,
            metadata={"embedding_dimensions": len(embed_result["embedding"])},
        ))
        total_cost += embed_result["cost_usd"]

        # Stage 2: RAG retrieval (multi-query expansion + injections run in-process)
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

        # Iterative quality refinement loop
        current_iteration = 1
        feedback = None
        answer_text = ""
        verified_claims = []
        accuracy_score = 0
        evaluations = []
        average_score = 0.0

        while current_iteration <= settings.max_iterations:
            logfire.info(f"Starting iteration {current_iteration}")

            # Stage 3: Answer generation (own retried task)
            gen_result = await generate_answer_task(question, documents_to_json(documents), feedback)
            stages.append(_stage_result(
                "answer_generation",
                iteration=current_iteration,
                cost_usd=gen_result["cost_usd"],
                tokens_used=gen_result["input_tokens"] + gen_result["output_tokens"],
                model=settings.answer_model,
                metadata={"answer_length": len(gen_result["answer"])},
            ))
            total_cost += gen_result["cost_usd"]
            answer_text = gen_result["answer"]

            # Stage 4: Claims extraction (own retried task)
            claims_result = await extract_claims_task(answer_text)
            stages.append(_stage_result(
                "claims_extraction",
                iteration=current_iteration,
                cost_usd=claims_result["cost_usd"],
                tokens_used=claims_result["input_tokens"] + claims_result["output_tokens"],
                model=settings.claims_model,
                metadata={"claims_extracted": len(claims_result["claims"])},
            ))
            total_cost += claims_result["cost_usd"]

            # Stage 5: Claims verification (own task; per-claim gather stays in-process inside it)
            verification_result = await verify_claims_task(claims_result["claims"])
            verified_claims = claims_from_json(verification_result["verified_claims"])
            verification_rate = verification_result["verification_rate"] * 100
            verified_count = len([c for c in verified_claims if c.verified])
            stages.append(_stage_result(
                "claims_verification",
                iteration=current_iteration,
                cost_usd=verification_result["cost_usd"],
                model=settings.embedding_model,
                metadata={
                    "claims_verified": verified_count,
                    "total_claims": len(verified_claims),
                    "verification_rate": f"{verification_rate:.0f}%",
                },
            ))
            total_cost += verification_result["cost_usd"]

            # Stages 6 + 7: accuracy + the two quality judges — three subtasks on
            # three parallel instances. The average score and inter-judge agreement
            # are combined here (the judges already ran through build_evaluation_result).
            stage_start = time.time()
            accuracy_result, openai_rate, anthropic_rate = await asyncio.gather(
                check_accuracy_task(answer_text, claims_to_json(verified_claims)),
                rate_quality_openai_task(question, answer_text, len(documents)),
                rate_quality_anthropic_task(question, answer_text, len(documents)),
            )
            parallel_duration = (time.time() - stage_start) * 1000

            accuracy_score = accuracy_result["accuracy_score"]
            openai_eval = EvaluationResult.model_validate(openai_rate["evaluation"])
            anthropic_eval = EvaluationResult.model_validate(anthropic_rate["evaluation"])
            evaluations = [openai_eval, anthropic_eval]
            average_score = (openai_eval.score + anthropic_eval.score) / 2
            score_difference = abs(openai_eval.score - anthropic_eval.score)
            agreement_level = "high" if score_difference <= 5 else "medium" if score_difference <= 15 else "low"
            eval_cost = openai_rate["cost_usd"] + anthropic_rate["cost_usd"]
            stages.append(_stage_result(
                "technical_accuracy",
                iteration=current_iteration,
                duration_ms=parallel_duration,
                cost_usd=accuracy_result["cost_usd"],
                tokens_used=accuracy_result["input_tokens"] + accuracy_result["output_tokens"],
                model=settings.accuracy_model,
                metadata={"accuracy_score": accuracy_score},
            ))
            total_cost += accuracy_result["cost_usd"]
            stages.append(_stage_result(
                "quality_evaluation",
                iteration=current_iteration,
                duration_ms=parallel_duration,
                cost_usd=eval_cost,
                model=f"{settings.eval_model_openai} + {settings.eval_model_anthropic}",
                metadata={
                    "quality_score": f"{average_score:.1f}",
                    "openai_score": openai_eval.score,
                    "claude_score": anthropic_eval.score,
                    "agreement": agreement_level,
                },
            ))
            total_cost += eval_cost

            # Stage 8: Quality gate
            gate_result = await quality_gate_decision(
                average_score=average_score,
                evaluations=evaluations,
                accuracy_score=accuracy_score,
                current_iteration=current_iteration,
                errors=accuracy_result["errors"],
                corrections=accuracy_result["corrections"],
            )
            stages.append(_stage_result(
                "quality_gate",
                iteration=current_iteration,
                cost_usd=0.0,
                metadata={
                    "should_iterate": gate_result["should_iterate"],
                    "reason": gate_result["reason"],
                },
            ))

            if not gate_result["should_iterate"]:
                logfire.info(f"Quality gate passed: {gate_result['reason']}")
                break

            logfire.info(f"Quality gate requires iteration: {gate_result['reason']}")
            feedback = gate_result["feedback"]
            current_iteration += 1

        total_duration_ms = (time.time() - pipeline_start) * 1000

        response = AnswerResponse(
            question=question,
            answer=answer_text,
            sources=documents,
            claims=verified_claims,
            quality_score=average_score,
            accuracy_score=accuracy_score,
            evaluations=evaluations,
            iterations=current_iteration,
            total_cost=total_cost,
            total_duration_ms=total_duration_ms,
            stages=stages,
            session_id=session_id,
        )

        # Persist the session here (the orchestrator already holds all the data
        # and has DB access), so the gateway need not re-receive everything.
        response.session_id = await _persist_session(response)

        track_pipeline_metrics(
            question=question,
            total_cost=total_cost,
            total_duration_ms=total_duration_ms,
            quality_score=average_score,
            accuracy_score=accuracy_score,
            iterations=current_iteration,
            session_id=response.session_id,
        )

        return response.model_dump(mode="json")


async def _persist_session(response: AnswerResponse) -> str | None:
    """Save the completed Q&A session to the database."""
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
            iterations=response.iterations,
            total_cost=response.total_cost,
            total_duration_ms=response.total_duration_ms,
            trace_id=trace_id,
            stages=[s.model_dump() for s in response.stages],
        )
        logfire.info(f"Saved session to database: {saved_id}", trace_id=trace_id)
        return saved_id
    except Exception as e:  # noqa: BLE001 - persistence is best-effort
        logfire.error(f"Failed to save session: {e}")
        return None


# ---------------------------------------------------------------------------
# Ingestion — parallel fan-out (replaces the sequential preDeployCommand)
# ---------------------------------------------------------------------------

async def _run_ingest_script(module_name: str) -> dict:
    """Import ``data.scripts.<module_name>``, run its ``main()``, report status."""
    import importlib

    module = importlib.import_module(f"data.scripts.{module_name}")
    await module.main()
    return {"task": module_name, "status": "ok"}


@app.task(timeout_seconds=1800)
async def ingest_core() -> dict:
    """Core documentation ingest (additive sync). Establishes the base schema/rows."""
    from data.scripts import ingest_docs

    await ingest_docs.main(sync=True)
    return {"task": "ingest_core", "status": "ok"}


# Each page injector is its own named, retried task so the fan-out below can run
# it on a separate instance — the bodies just delegate to _run_ingest_script.

@app.task
async def add_pricing() -> dict:
    """Inject the pricing page."""
    return await _run_ingest_script("add_pricing_page")


@app.task
async def add_workflows_tutorial() -> dict:
    """Inject the Workflows tutorial page."""
    return await _run_ingest_script("add_workflows_tutorial_page")


@app.task
async def add_workflows_docs() -> dict:
    """Inject the Workflows docs page."""
    return await _run_ingest_script("add_workflows_docs_page")


@app.task
async def add_autoscaling() -> dict:
    """Inject the autoscaling page."""
    return await _run_ingest_script("add_autoscaling_page")


@app.task
async def add_nodejs() -> dict:
    """Inject the Node.js page."""
    return await _run_ingest_script("add_nodejs_page")


@app.task
async def add_tutorials_index() -> dict:
    """Inject the tutorials index page."""
    return await _run_ingest_script("add_tutorials_index_page")


@app.task(timeout_seconds=3600)
async def ingest_all() -> dict:
    """Run the full ingestion as a parallel fan-out.

    ``ingest_core`` runs first to establish the base schema/rows, then the six
    independent page-injection tasks fan out concurrently — replacing the old
    7-script sequential ``&&`` chain.
    """
    core = await ingest_core()

    page_results = await asyncio.gather(
        add_pricing(),
        add_workflows_tutorial(),
        add_workflows_docs(),
        add_autoscaling(),
        add_nodejs(),
        add_tutorials_index(),
    )

    return {"core": core, "pages": list(page_results)}


if __name__ == "__main__":
    app.start()
