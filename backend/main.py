"""FastAPI gateway for Ask Render Anything Assistant.

The Q&A pipeline runs in a separate Render Workflows service. This gateway is a
thin client: ``POST /ask`` triggers a workflow run and ``GET /ask/{run_id}``
polls it for the result. It also serves health, stats, and session history.
"""

from contextlib import asynccontextmanager
from functools import lru_cache
from uuid import uuid4

# Export .env into os.environ before importing the Render SDK. The SDK reads
# RENDER_USE_LOCAL_DEV (and other SDK-only vars) via os.getenv(), but pydantic-settings
# loads .env into Settings only — it never populates os.environ. Without this, local dev
# falls through to https://api.render.com instead of the local dev server on :8120. In
# cloud there is no .env file, so this is a no-op.
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logfire

# Importing observability configures Logfire + instrumentation at module load.
import backend.observability  # noqa: F401

from render_sdk import RenderAsync
from render_sdk.client.errors import RenderError
from render_sdk.client.types import TaskRunStatusValues

from backend.config import settings
from backend.models import QuestionRequest, HealthCheck
from backend.database import vector_store
from backend.api.logs import fetch_logfire_logs


@lru_cache(maxsize=1)
def get_render() -> RenderAsync:
    """Lazily build a single async Render client for triggering/polling runs."""
    return RenderAsync(token=settings.render_api_key or None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""

    # Startup
    logfire.info("Starting Ask Render Anything Assistant")
    await vector_store.initialize()
    logfire.info("Application started successfully")

    yield

    # Shutdown
    logfire.info("Shutting down Ask Render Anything Assistant")
    await vector_store.close()
    logfire.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Ask Render Anything Assistant",
    description="Production-grade AI pipeline with observable AI using Pydantic AI, Logfire, and Render",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument FastAPI with Logfire for automatic HTTP tracing
logfire.instrument_fastapi(app)


@app.get("/", tags=["Health"])
async def root():
    """Root endpoint."""
    return {
        "name": "Ask Render Anything Assistant",
        "version": "1.0.0",
        "status": "operational"
    }


@app.get("/health", response_model=HealthCheck, tags=["Health"])
async def health_check():
    """Health check endpoint."""

    db_healthy = await vector_store.health_check()

    return HealthCheck(
        status="healthy" if db_healthy else "degraded",
        database_connected=db_healthy,
        logfire_enabled=True
    )


@app.post("/ask", status_code=202, tags=["Q&A"])
async def ask_question(request: QuestionRequest):
    """
    Trigger the Q&A pipeline workflow for a question.

    The pipeline runs asynchronously in the Render Workflows service. This
    returns a ``run_id`` immediately; poll ``GET /ask/{run_id}`` for the result.
    """

    if not settings.workflow_slug:
        raise HTTPException(status_code=503, detail="WORKFLOW_SLUG is not configured")

    with logfire.span(
        "user_session.qa_request",
        session_id=request.session_id or "anonymous",
        question=request.question[:100],
        question_length=len(request.question),
    ):
        try:
            render = get_render()
            # Opaque token the workflow writes live per-stage progress under, so the
            # poll endpoint can surface real stage-by-stage feedback to the UI. The
            # orchestrator can't discover its own run id, so we correlate by token.
            progress_token = str(uuid4())
            task_run = await render.workflows.start_task(
                f"{settings.workflow_slug}/run_qa_pipeline",
                {
                    "question": request.question,
                    "session_id": request.session_id,
                    "progress_token": progress_token,
                },
            )
            logfire.info(
                "Triggered Q&A workflow run",
                run_id=task_run.id,
                session_id=request.session_id or "anonymous",
            )
            return {"run_id": task_run.id, "progress_token": progress_token, "status": "pending"}

        except RenderError as e:
            logfire.error("Failed to trigger workflow run", error=str(e), exc_info=True)
            raise HTTPException(status_code=502, detail=f"Failed to start pipeline: {e}")


@app.get("/ask/{run_id}", tags=["Q&A"])
async def get_answer(run_id: str, progress_token: str | None = None):
    """
    Poll a Q&A workflow run.

    Returns ``{"status": "running"}`` while in progress, ``{"status": "done",
    "result": <AnswerResponse>}`` on success, or ``{"status": "failed",
    "error": ...}`` if the run failed. When ``progress_token`` is supplied, the
    cumulative per-stage progress recorded so far is returned as ``updates`` so
    the UI can show real stage-by-stage feedback while the run is in flight.
    """

    # Live per-stage progress (best-effort — never fail the poll over it).
    updates: list[dict] = []
    if progress_token:
        try:
            updates = await vector_store.get_progress(progress_token)
        except Exception as e:  # noqa: BLE001
            logfire.warning(f"Failed to read progress: {e}")

    try:
        details = await get_render().workflows.get_task_run(run_id)
    except RenderError as e:
        raise HTTPException(status_code=404, detail=f"Run not found: {e}")

    status = details.status.value if hasattr(details.status, "value") else details.status

    if status in (TaskRunStatusValues.SUCCEEDED, TaskRunStatusValues.COMPLETED):
        # The orchestrator returns a single AnswerResponse dict; results is a list.
        result = details.results[0] if details.results else None
        return {"status": "done", "result": result, "updates": updates}

    if status in (TaskRunStatusValues.FAILED, TaskRunStatusValues.CANCELED):
        error = getattr(details, "error", None) or f"Run {status}"
        return {"status": "failed", "error": str(error), "updates": updates}

    return {"status": "running", "updates": updates}


@app.get("/stats", tags=["Admin"])
async def get_stats():
    """Get database statistics."""

    doc_count = await vector_store.get_document_count()

    return {
        "document_count": doc_count,
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "rag_top_k": settings.rag_top_k
    }


@app.get("/history", tags=["Q&A"])
async def get_history(limit: int = 20):
    """
    Get recent Q&A sessions.

    Args:
        limit: Maximum number of sessions to return (default: 20, max: 100)
    """

    if limit > 100:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 100")

    sessions = await vector_store.get_recent_sessions(limit=limit)

    return {
        "sessions": sessions,
        "count": len(sessions)
    }


@app.get("/history/{session_id}", tags=["Q&A"])
async def get_session(session_id: str):
    """
    Get a specific Q&A session by ID.

    Args:
        session_id: The UUID of the session
    """

    session = await vector_store.get_session_by_id(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@app.delete("/history/{session_id}", tags=["Q&A"])
async def delete_session(session_id: str):
    """
    Delete a specific Q&A session by ID.

    Args:
        session_id: The UUID of the session to delete
    """

    deleted = await vector_store.delete_session(session_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "message": "Session deleted successfully",
        "session_id": session_id
    }


@app.delete("/history", tags=["Q&A"])
async def clear_all_history():
    """
    Delete all Q&A sessions from history.

    This action cannot be undone.
    """

    deleted_count = await vector_store.delete_all_sessions()

    return {
        "success": True,
        "message": f"Deleted {deleted_count} sessions",
        "count": deleted_count
    }


@app.get("/sessions/{session_id}/logs", tags=["Observability"])
async def get_session_logs(session_id: str):
    """
    Fetch Logfire logs for a specific Q&A session.

    Returns detailed observability logs from Logfire for the given session,
    including all spans, traces, and metrics captured during execution.
    """
    # Get session from database to retrieve trace_id
    session = await vector_store.get_session_by_id(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    trace_id = session.get('trace_id')
    if not trace_id:
        raise HTTPException(
            status_code=404,
            detail="Trace ID not available for this session (may be from before trace logging was enabled)"
        )

    # Fetch logs from Logfire API
    try:
        logs_data = await fetch_logfire_logs(trace_id)
        return logs_data
    except HTTPException:
        raise
    except Exception as e:
        logfire.error(f"Unexpected error fetching logs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower()
    )
