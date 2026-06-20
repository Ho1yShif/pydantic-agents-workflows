"""Logfire configuration and instrumentation."""

import logfire
from logfire import LogfireSpan
from typing import Any, Callable, TypeVar
try:
    from typing import ParamSpec
except ImportError:
    from typing_extensions import ParamSpec
from functools import wraps
import time
from contextlib import asynccontextmanager

from backend.config import settings

# Configure Logfire
logfire.configure(
    token=settings.logfire_token,
    service_name="render-qa-assistant",
    environment="production",
)

# Auto-instrument libraries globally
logfire.instrument_openai()       # Instruments direct OpenAI clients (embeddings.py)
logfire.instrument_pydantic_ai()  # Instruments pydantic-ai agents (all LLM pipeline stages)
logfire.instrument_asyncpg()      # Database queries
logfire.instrument_httpx()        # HTTP client requests
logfire.instrument_system_metrics()  # System metrics (CPU, memory, swap)
# Note: FastAPI instrumentation is done in main.py after app creation


P = ParamSpec('P')
R = TypeVar('R')


def instrument_stage(stage_name: str):
    """Decorator to instrument a pipeline stage with Logfire."""
    
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with logfire.span(
                stage_name
            ) as span:
                span.set_attribute("span_type", "pipeline_stage")
                start_time = time.time()
                
                try:
                    result = await func(*args, **kwargs)
                    
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)
                    span.set_attribute("success", True)
                    
                    # Add cost if available
                    if isinstance(result, dict) and "cost_usd" in result:
                        span.set_attribute("cost_usd", result["cost_usd"])
                    
                    # Add token usage if available
                    if isinstance(result, dict):
                        if "input_tokens" in result:
                            span.set_attribute("input_tokens", result["input_tokens"])
                        if "output_tokens" in result:
                            span.set_attribute("output_tokens", result["output_tokens"])
                    
                    return result
                    
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)
                    span.set_attribute("success", False)
                    span.set_attribute("error", str(e))
                    logfire.error(f"Stage {stage_name} failed: {e}")
                    raise
        
        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with logfire.span(
                stage_name
            ) as span:
                span.set_attribute("span_type", "pipeline_stage")
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)
                    span.set_attribute("success", True)
                    
                    return result
                    
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration_ms", duration_ms)
                    span.set_attribute("success", False)
                    span.set_attribute("error", str(e))
                    logfire.error(f"Stage {stage_name} failed: {e}")
                    raise
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            return sync_wrapper  # type: ignore
    
    return decorator


@asynccontextmanager
async def pipeline_trace(question: str):
    """Context manager for tracing an entire pipeline execution."""
    
    with logfire.span(
        "qa_pipeline",
        question=question
    ) as span:
        span.set_attribute("span_type", "pipeline")
        start_time = time.time()
        pipeline_context = {
            "span": span,
            "start_time": start_time,
            "total_cost": 0.0,
            "stages": []
        }
        
        try:
            yield pipeline_context
            
            duration_ms = (time.time() - start_time) * 1000
            span.set_attribute("duration_ms", duration_ms)
            span.set_attribute("total_cost_usd", pipeline_context["total_cost"])
            span.set_attribute("success", True)
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            span.set_attribute("duration_ms", duration_ms)
            span.set_attribute("success", False)
            span.set_attribute("error", str(e))
            logfire.error(f"Pipeline failed: {e}")
            raise


def calculate_embedding_cost(tokens: int) -> float:
    """Calculate cost for embedding API calls."""
    from backend.prices import get_price
    from backend.config import settings
    price = get_price(settings.embedding_model)
    return (tokens / 1_000_000) * price.input_cost_per_m


def calculate_openai_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost for OpenAI API calls."""
    from backend.prices import get_price
    price = get_price(model)
    return (input_tokens / 1_000_000) * price.input_cost_per_m + \
           (output_tokens / 1_000_000) * price.output_cost_per_m


def calculate_anthropic_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost for Anthropic API calls."""
    from backend.prices import get_price
    price = get_price(model)
    return (input_tokens / 1_000_000) * price.input_cost_per_m + \
           (output_tokens / 1_000_000) * price.output_cost_per_m


def track_pipeline_metrics(
    question: str,
    total_cost: float,
    total_duration_ms: float,
    quality_score: float,
    accuracy_score: float,
    iterations: int,
    session_id: str = None
):
    """
    Track custom business metrics for the pipeline execution.
    
    These metrics enable analysis of:
    - Cost trends and optimization opportunities
    - Quality score distributions
    - Performance characteristics
    - Iteration patterns
    """
    
    # Track total cost per request
    logfire.metric_histogram("pipeline.cost.total", unit="USD").record(
        total_cost,
        attributes={
            "iterations": iterations,
            "session_id": session_id or "unknown",
        },
    )
    
    # Track cost per iteration (normalized)
    cost_per_iteration = total_cost / iterations if iterations > 0 else total_cost
    logfire.metric_histogram("pipeline.cost.per_iteration", unit="USD").record(
        cost_per_iteration,
        attributes={
            "iterations": iterations,
            "session_id": session_id or "unknown",
        },
    )
    
    # Track pipeline duration
    logfire.metric_histogram("pipeline.duration", unit="ms").record(
        total_duration_ms,
        attributes={
            "iterations": iterations,
            "session_id": session_id or "unknown",
        },
    )
    
    # Track quality score distribution
    logfire.metric_histogram("pipeline.quality_score", unit="score").record(
        quality_score,
        attributes={
            "iterations": iterations,
            "passed_first_iteration": iterations == 1,
            "session_id": session_id or "unknown",
        },
    )
    
    # Track accuracy score
    logfire.metric_histogram("pipeline.accuracy_score", unit="score").record(
        accuracy_score,
        attributes={
            "iterations": iterations,
            "session_id": session_id or "unknown",
        },
    )
    
    # Track iteration count distribution
    logfire.metric_histogram("pipeline.iterations", unit="count").record(
        iterations,
        attributes={
            "quality_score_bucket": f"{int(quality_score // 10) * 10}-{int(quality_score // 10) * 10 + 10}",
            "session_id": session_id or "unknown",
        },
    )
    
    # Log structured event for queryability
    logfire.info(
        "Pipeline execution completed",
        question_length=len(question),
        total_cost_usd=total_cost,
        duration_ms=total_duration_ms,
        quality_score=quality_score,
        accuracy_score=accuracy_score,
        iterations=iterations,
        cost_per_iteration=cost_per_iteration,
        passed_first_iteration=iterations == 1,
        session_id=session_id or "unknown",
    )

