"""Stage 5: Claims Verification."""

import asyncio
from typing import List

from pydantic_ai import Embedder, EmbeddingSettings
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.config import settings, PipelineConfig
from backend.database import vector_store
from backend.models import Claim, ClaimVerdict
from backend.observability import instrument_stage, calculate_embedding_cost, calculate_openai_cost
from backend.pipeline._agents import openai_agent
import logfire


# Pydantic AI embedder (auto-instrumented by logfire.instrument_pydantic_ai())
embedder = Embedder(
    OpenAIEmbeddingModel(
        settings.embedding_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
        settings=EmbeddingSettings(dimensions=settings.embedding_dimensions),
    )
)


# Number of candidate passages to surface to the entailment judge per claim.
# 10 (not 5) gives the judge the correctly-retrieved chunk plus a few neighbors;
# cheap insurance now that the HNSW index actually returns the true nearest matches.
_CANDIDATE_K = 10


VERIFICATION_INSTRUCTIONS = """You verify whether a single factual claim about Render's platform is \
substantiated by the provided documentation passages.

Rules:
- Return supported=true ONLY if at least one passage directly substantiates the claim. Paraphrases and \
clear logical entailment count; loosely-related or merely on-topic passages do NOT.
- confidence (0.0-1.0) reflects how directly and completely the passages support the claim: ~0.9-1.0 when a \
passage states it almost verbatim, ~0.6-0.8 when it is clearly implied, lower when support is partial.
- If nothing substantiates the claim, return supported=false with confidence 0.0.
- supporting_doc_indices: the 1-based indices of the passages that substantiate the claim (empty if none).
- Use ONLY the provided passages. Do NOT rely on outside knowledge."""


_verification_agent = openai_agent(
    settings.claims_model, VERIFICATION_INSTRUCTIONS, output_type=ClaimVerdict
)


async def _verify_claim_with_embedding(claim_text: str, embedding: list) -> tuple[Claim, int, int]:
    """Verify a claim via LLM entailment over the passages retrieved for it.

    Retrieval (using the pre-computed embedding) gathers candidate evidence; an LLM
    then judges whether the docs actually substantiate the claim. Returns the Claim
    plus (input_tokens, output_tokens) so the caller can total the cost.
    """
    docs = await vector_store.similarity_search(
        query_embedding=embedding,
        k=_CANDIDATE_K,
        threshold=settings.verification_threshold,
    )

    # No candidate evidence above the floor -> honestly unsupported.
    if not docs:
        logfire.debug(f"Claim verification: '{claim_text[:50]}...' - no candidates, unsupported")
        return Claim(claim=claim_text, verified=False, verification_score=0.0, supporting_docs=[]), 0, 0

    passages = "\n\n".join(
        f"[Passage {i}] Source: {doc.source}\n{doc.content}"
        for i, doc in enumerate(docs, 1)
    )
    user_prompt = f"""Claim:
{claim_text}

Documentation passages:
{passages}

Decide whether the passages substantiate the claim."""

    result = await _verification_agent.run(
        user_prompt,
        model_settings={"temperature": 0.0, "max_tokens": 500},
    )
    verdict: ClaimVerdict = result.output
    usage = result.usage()
    input_tokens = usage.request_tokens or 0
    output_tokens = usage.response_tokens or 0

    # Map the cited passage indices back to their sources (guard against out-of-range).
    # If the judge supports the claim but names no passage, we leave the citation list
    # empty rather than fabricating one from the top retrieved doc — an honest
    # "verified, no specific source cited" beats a possibly-wrong attribution.
    cited = [docs[i - 1].source for i in verdict.supporting_doc_indices if 1 <= i <= len(docs)]

    verification_score = verdict.confidence if verdict.supported else 0.0

    logfire.debug(
        f"Claim verification: '{claim_text[:50]}...' - verified={verdict.supported}, "
        f"score={verification_score:.3f}, candidates={len(docs)}, cited={len(cited)}"
    )

    return (
        Claim(
            claim=claim_text,
            verified=verdict.supported,
            verification_score=verification_score,
            supporting_docs=cited[:2],
        ),
        input_tokens,
        output_tokens,
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

    if not claims:
        return {"verified_claims": [], "verification_rate": 0.0, "cost_usd": 0.0}

    # Batch embed all claims in a single API call
    batch_result = await embedder.embed_documents(claims)
    embeddings = [list(e) for e in batch_result.embeddings]
    total_tokens = batch_result.usage.input_tokens

    # Verify all claims in parallel: retrieve candidate passages, then LLM entailment.
    results = await asyncio.gather(*[
        _verify_claim_with_embedding(c, e) for c, e in zip(claims, embeddings)
    ])
    verified_claims: List[Claim] = [r[0] for r in results]

    # Calculate costs: claim embeddings + the per-claim entailment LLM calls
    judge_input_tokens = sum(r[1] for r in results)
    judge_output_tokens = sum(r[2] for r in results)
    cost_usd = (
        calculate_embedding_cost(total_tokens)
        + calculate_openai_cost(judge_input_tokens, judge_output_tokens, settings.claims_model)
    )

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
        "tokens_used": judge_input_tokens + judge_output_tokens,
    }
