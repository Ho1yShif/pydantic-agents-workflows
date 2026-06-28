"""FastAPI app for Ask Render Anything Assistant.

The Q&A pipeline runs in-process: ``POST /ask`` launches the pipeline as a
background task and returns a ``run_id`` immediately; ``GET /ask/{run_id}`` polls
for live per-stage progress and the final result. It also serves health, stats,
and session history.
"""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

# Load .env for local development (no-op in cloud, where there is no .env file).
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logfire

# Importing observability configures Logfire + instrumentation at module load.
import backend.observability  # noqa: F401

from backend.config import settings
from backend.models import QuestionRequest, HealthCheck
from backend.database import vector_store
from backend.pipeline.orchestrator import run_qa_pipeline
from backend.api.logs import fetch_logfire_logs


# Strong references to in-flight background pipeline tasks. asyncio holds only a
# weak reference to a task, so without this set a run could be garbage-collected
# mid-flight; each task removes itself on completion.
_background_tasks: set[asyncio.Task] = set()


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


async def _run_pipeline_task(run_id: str, request: QuestionRequest, progress_token: str) -> None:
    """Background task: run the in-process pipeline and record its terminal state.

    Wrapped in the same logfire span the request opened so the run stays on one
    trace, and never raises — any failure is captured as a ``failed`` run row that
    the poll endpoint surfaces to the UI.
    """
    with logfire.span(
        "user_session.qa_request",
        session_id=request.session_id or "anonymous",
        client_id=request.client_id or "anonymous",
        question=request.question[:100],
        question_length=len(request.question),
    ):
        try:
            response = await run_qa_pipeline(
                question=request.question,
                session_id=request.session_id,
                client_id=request.client_id,
                progress_token=progress_token,
            )
            await vector_store.set_run_status(
                run_id, "done", result=response.model_dump(mode="json")
            )
        except Exception as e:  # noqa: BLE001 - surface failures via the run row
            logfire.error("Q&A pipeline run failed", error=str(e), exc_info=True)
            try:
                await vector_store.set_run_status(run_id, "failed", error=str(e))
            except Exception as inner:  # noqa: BLE001
                logfire.error(f"Failed to record run failure: {inner}")


@app.post("/ask", status_code=202, tags=["Q&A"])
async def ask_question(request: QuestionRequest):
    """
    Start the Q&A pipeline for a question.

    The pipeline runs in-process as a background task. This returns a ``run_id``
    immediately; poll ``GET /ask/{run_id}`` for live progress and the result.
    """

    # `run_id` doubles as the progress token: one opaque id correlates the run row
    # (status + result) and the per-stage progress the orchestrator records.
    run_id = str(uuid4())
    await vector_store.set_run_status(run_id, "running")

    task = asyncio.create_task(_run_pipeline_task(run_id, request, run_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"run_id": run_id, "progress_token": run_id, "status": "pending"}


@app.get("/ask/{run_id}", tags=["Q&A"])
async def get_answer(run_id: str, progress_token: str | None = None):
    """
    Poll an in-process Q&A run.

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

    run = await vector_store.get_run_status(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if run["status"] == "done":
        return {"status": "done", "result": run["result"], "updates": updates}

    if run["status"] == "failed":
        return {"status": "failed", "error": run["error"] or "Pipeline run failed", "updates": updates}

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
async def get_history(client_id: str, limit: int = 20):
    """
    Get recent Q&A sessions for the calling browser client.

    Args:
        client_id: Anonymous browser client ID to scope history to.
        limit: Maximum number of sessions to return (default: 20, max: 100)
    """

    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")

    if limit > 100:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 100")

    sessions = await vector_store.get_recent_sessions(client_id=client_id, limit=limit)

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
async def delete_session(session_id: str, client_id: str):
    """
    Delete a specific Q&A session by ID, scoped to the calling client.

    Args:
        session_id: The UUID of the session to delete
        client_id: Anonymous browser client ID that must own the session
    """

    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")

    deleted = await vector_store.delete_session(session_id, client_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "success": True,
        "message": "Session deleted successfully",
        "session_id": session_id
    }


@app.delete("/history", tags=["Q&A"])
async def clear_all_history(client_id: str):
    """
    Delete all Q&A sessions owned by the calling client.

    This action cannot be undone.

    Args:
        client_id: Anonymous browser client ID whose history is cleared
    """

    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")

    deleted_count = await vector_store.delete_all_sessions(client_id)

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
