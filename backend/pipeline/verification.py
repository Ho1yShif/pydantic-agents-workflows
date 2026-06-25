"""Stage 5: Claims Verification."""

import asyncio
from typing import List

from pydantic_ai import Embedder, EmbeddingSettings
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import settings, PipelineConfig
from backend.database import vector_store
from backend.models import Claim
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


async def _verify_claim_with_embedding(claim_text: str, embedding: list) -> Claim:
    """Check a claim against the vector store using a pre-computed embedding."""
    docs = await vector_store.similarity_search(
        query_embedding=embedding,
        k=5,
        threshold=0.3,
    )

    verified = False
    verification_score = 0.0
    supporting_docs = []

    if docs:
        verification_score = docs[0].similarity_score

        # BOOST: Prioritize pricing table sources for pricing-related claims
        is_pricing_claim = any(
            term in claim_text.lower()
            for term in ["$", "pricing", "price", "cost", "plan", "tier", "gb", "ram", "cpu"]
        )
        is_pricing_source = docs[0].source == "https://render.com/pricing"

        if is_pricing_claim and is_pricing_source:
            verification_score = min(1.0, verification_score * 1.1)
            logfire.debug(f"Boosted pricing claim verification: {verification_score:.3f}")

        verified = verification_score >= settings.verification_threshold

        verified_docs = [doc for doc in docs if doc.similarity_score >= settings.verification_threshold]
        supporting_docs = [doc.source for doc in verified_docs[:2]]

        if verified_docs:
            verification_score = max(verification_score, verified_docs[0].similarity_score)

    logfire.debug(
        f"Claim verification: '{claim_text[:50]}...' - verified={verified}, "
        f"score={verification_score:.3f}, docs_found={len(docs)}, "
        f"verified_docs={len(supporting_docs)}, threshold={settings.verification_threshold}"
    )

    return Claim(
        claim=claim_text,
        verified=verified,
        verification_score=verification_score,
        supporting_docs=supporting_docs,
    )


@instrument_stage(PipelineConfig.STAGE_VERIFICATION)
async def verify_claims(claims: List[str]) -> dict:
    """
    Verify each claim against documentation using RAG.

    Args:
        claims: List of claim strings to verify

    Returns:
        dict with 'verified_claims', 'verification_rate', 'cost_usd'
    """

    logfire.info(f"Verifying {len(claims)} claims")

    # Batch embed all claims in a single API call
    batch_result = await embedder.embed_documents(claims)
    embeddings = [list(e) for e in batch_result.embeddings]
    total_tokens = batch_result.usage.input_tokens

    # Verify all claims in parallel using pre-computed embeddings
    verified_claims: List[Claim] = await asyncio.gather(*[
        _verify_claim_with_embedding(c, e) for c, e in zip(claims, embeddings)
    ])

    # Calculate costs
    cost_usd = calculate_embedding_cost(total_tokens) + (len(claims) * 0.0001)

    # Calculate verification rate
    verified_count = sum(1 for c in verified_claims if c.verified)
    verification_rate = verified_count / len(verified_claims) if verified_claims else 0.0

    logfire.info(
        "Claims verified",
        total_claims=len(verified_claims),
        verified_count=verified_count,
        verification_rate=verification_rate,
        cost_usd=cost_usd,
    )

    return {
        "verified_claims": verified_claims,
        "verification_rate": verification_rate,
        "cost_usd": cost_usd,
    }
