"""Stage 1: Question Embedding."""

from pydantic_ai import Embedder, EmbeddingSettings
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import settings, PipelineConfig
from backend.observability import instrument_stage, calculate_embedding_cost
import logfire


# Pydantic AI embedder (auto-instrumented by logfire.instrument_pydantic_ai())
embedder = Embedder(
    OpenAIEmbeddingModel(
        settings.embedding_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
        settings=EmbeddingSettings(dimensions=settings.embedding_dimensions),
    )
)


@instrument_stage(PipelineConfig.STAGE_EMBEDDING)
async def embed_question(question: str) -> dict:
    """
    Convert natural language question to vector representation.

    Args:
        question: The user's question

    Returns:
        dict with 'embedding', 'tokens', 'cost_usd'
    """

    logfire.info(f"Embedding question: {question[:100]}...")

    result = await embedder.embed_query(question)

    embedding = list(result.embeddings[0])
    tokens = result.usage.input_tokens
    cost_usd = calculate_embedding_cost(tokens)

    logfire.info(
        "Question embedded",
        tokens=tokens,
        cost_usd=cost_usd,
        embedding_length=len(embedding),
    )

    return {
        "embedding": embedding,
        "tokens": tokens,
        "cost_usd": cost_usd,
    }
