"""Stage 2: RAG Document Retrieval with Multi-Query Expansion."""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import List, Optional

from backend.config import settings, PipelineConfig
from backend.database import vector_store
from backend.models import Document
from backend.observability import instrument_stage
from backend.pipeline.embeddings import embed_question
from backend.pipeline.query_expansion import expand_query, should_expand_query
import logfire


# Score for an editorially-injected curated doc: the top of the cosine scale, so it
# ranks first. It is NOT a measured similarity — it marks a doc we deliberately surface
# for a topic. A curated doc is only injected when retrieval did NOT already find it
# (see inject_curated_docs), so this never disguises a real search result.
INJECTED_DOC_SCORE = 1.0

# All pricing tables live under this source and are distinguished by title.
PRICING_SOURCE = "https://render.com/pricing"


# Pricing keywords that trigger explicit pricing table injection
PRICING_KEYWORDS = [
    'pricing', 'price', 'cost', 'costs', 'plan', 'plans', 'tier', 'tiers',
    'instance type', 'instance types', '$', 'dollar', 'monthly', 'per month',
    'how much', 'what does it cost'
]

PRODUCT_KEYWORDS = {
    'postgres': ['Render Postgres Pricing'],
    'postgresql': ['Render Postgres Pricing'],
    'database': ['Render Postgres Pricing', 'Render Key Value Pricing'],
    'datastore': ['Render Postgres Pricing', 'Render Key Value Pricing'],
    'key value': ['Render Key Value Pricing'],
    'keyvalue': ['Render Key Value Pricing'],
    'redis': ['Render Key Value Pricing'],
    'valkey': ['Render Key Value Pricing'],
    'web service': ['Render Web Services Pricing'],
    'private service': ['Render Web Services Pricing'],
    'background worker': ['Render Web Services Pricing'],
    'cron': ['Render Cron Jobs Pricing'],
    'cron job': ['Render Cron Jobs Pricing'],
}

# AI/agent keywords that trigger the Render Workflows agents tutorial injection
AI_AGENT_KEYWORDS = [
    'ai agent', 'ai agents', 'llm agent', 'llm', 'language model',
    'artificial intelligence', 'machine learning', 'deploy ai', 'deploy agent',
    'long-running', 'long running', 'self-orchestrating', 'render workflows',
    'agent workflow', 'agent deployment', 'agentic',
]

# Single-word AI keywords matched with word boundaries to avoid false positives.
# 'ai' is matched with word boundaries so it triggers on "ai" but not "email"/"detail".
AI_AGENT_SINGLE_WORD_KEYWORDS = ['agent', 'agents', 'ai']

# Two authoritative AI/agent sources are injected together:
#   1. the Workflows agents tutorial, and
#   2. the official Workflows docs (gives the verification + accuracy stages
#      authoritative material to check the generated answer against).
AI_AGENT_WORKFLOWS_SOURCE = "https://render.com/tutorials/agents-on-render-workflows/what-youll-build"
AI_AGENT_WORKFLOWS_DOCS_SOURCE = "https://render.com/docs/workflows"

# Autoscaling keywords
AUTOSCALING_KEYWORDS = [
    'autoscaling', 'autoscale', 'auto-scaling', 'auto scaling',
    'horizontal scaling', 'scale automatically', 'automatically scale',
    'scale up', 'scale down', 'min instances', 'max instances',
    'scaling policy', 'scale based on',
]
AUTOSCALING_SINGLE_WORD_KEYWORDS = ['scaling']
AUTOSCALING_DOC_SOURCE = "https://render.com/docs/scaling"

# Node.js deployment keywords
NODEJS_KEYWORDS = [
    'node.js', 'nodejs', 'node js', 'express', 'deploy node',
    'npm start', 'npm install', 'next.js', 'nextjs', 'deploy next',
    'vite', 'javascript app', 'js app', 'deploy javascript',
]
NODEJS_SINGLE_WORD_KEYWORDS = ['node']
NODEJS_DOC_SOURCE = "https://render.com/docs/deploy-node-express-app"

# Tutorials keywords that trigger the render.com/tutorials index recommendation
TUTORIALS_KEYWORDS = ['tutorial', 'tutorials']
TUTORIALS_INDEX_SOURCE = "https://render.com/tutorials"


# ---------------------------------------------------------------------------
# Curated document injection — data-driven
#
# Certain topics have an authoritative doc we always want in context, even if
# semantic search ranks it low. Rather than a detect_*/inject_* function pair per
# topic (all duplicating the same fetch → parse-metadata → prepend boilerplate),
# the topics are declared as data in INJECTION_RULES and a single helper
# (inject_curated_docs) does the work. Add a topic by adding a row, not a function.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocLookup:
    """Identifies one curated doc to fetch — by source URL, or by title within the
    pricing page (all pricing tables share PRICING_SOURCE and differ only by title)."""
    source: Optional[str] = None
    title: Optional[str] = None


@dataclass(frozen=True)
class InjectionRule:
    """A keyword trigger → curated docs to prepend when the question matches."""
    name: str
    keywords: tuple = ()           # phrase/substring keywords
    word_keywords: tuple = ()      # single words, matched with \b word boundaries
    lookups: tuple = ()            # DocLookup entries to fetch when matched


INJECTION_RULES = (
    InjectionRule(
        name="ai_agent",
        keywords=tuple(AI_AGENT_KEYWORDS),
        word_keywords=tuple(AI_AGENT_SINGLE_WORD_KEYWORDS),
        # Tutorial first (leads the context), docs second (verification material).
        lookups=(
            DocLookup(source=AI_AGENT_WORKFLOWS_SOURCE),
            DocLookup(source=AI_AGENT_WORKFLOWS_DOCS_SOURCE),
        ),
    ),
    InjectionRule(
        name="autoscaling",
        keywords=tuple(AUTOSCALING_KEYWORDS),
        word_keywords=tuple(AUTOSCALING_SINGLE_WORD_KEYWORDS),
        lookups=(DocLookup(source=AUTOSCALING_DOC_SOURCE),),
    ),
    InjectionRule(
        name="nodejs",
        keywords=tuple(NODEJS_KEYWORDS),
        word_keywords=tuple(NODEJS_SINGLE_WORD_KEYWORDS),
        lookups=(DocLookup(source=NODEJS_DOC_SOURCE),),
    ),
    InjectionRule(
        name="tutorials",
        # "tutorial"/"tutorials" matched with word boundaries (as the old code did).
        word_keywords=tuple(TUTORIALS_KEYWORDS),
        lookups=(DocLookup(source=TUTORIALS_INDEX_SOURCE),),
    ),
)


def _matches(question_lower: str, keywords: tuple, word_keywords: tuple) -> bool:
    """True if the question contains any phrase keyword or any word-boundary keyword."""
    if any(keyword in question_lower for keyword in keywords):
        return True
    return any(
        re.search(r'\b' + re.escape(word) + r'\b', question_lower)
        for word in word_keywords
    )


def _parse_metadata(raw) -> dict:
    """JSONB metadata may come back as a string, None, or dict — normalize to dict."""
    if isinstance(raw, str):
        return json.loads(raw)
    return raw or {}


async def _fetch_curated_docs(conn, lookup: DocLookup) -> List[Document]:
    """Fetch the curated doc(s) for a lookup — by (pricing-page) title or by source.

    Source-based lookups return ALL rows for the source: curated pages are now
    chunked into multiple rows, and every chunk should be injected so generation
    sees the whole page rather than one arbitrary chunk. Title-based (pricing)
    lookups still resolve to their single table doc.
    """
    if lookup.title is not None:
        rows = await conn.fetch(
            """
            SELECT content, source, title, section, metadata
            FROM documents
            WHERE title = $1 AND source = $2
            """,
            lookup.title, PRICING_SOURCE,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT content, source, title, section, metadata
            FROM documents
            WHERE source = $1
            """,
            lookup.source,
        )

    docs: List[Document] = []
    for row in rows:
        metadata = _parse_metadata(row['metadata'])
        docs.append(Document(
            content=row['content'],
            source=row['source'],
            metadata={
                'title': row['title'],
                'section': row['section'] or row['title'],
                **metadata,
            },
            similarity_score=INJECTED_DOC_SCORE,
        ))
    return docs


def detect_pricing_query(question: str) -> List[str]:
    """
    Detect if question is asking about pricing/plans and which products.

    Returns list of pricing table titles to explicitly inject. Kept as its own
    function (rather than a flat rule) because pricing needs a product → table map
    plus smart defaults that a single keyword list can't express.
    """
    question_lower = question.lower()

    # IMPORTANT: Don't trigger on "tier" if it's part of "free tier" (that's about instance behavior, not pricing)
    if "free tier" in question_lower or "free instance" in question_lower:
        # This is a question about free tier behavior, not pricing
        return []

    # Check if pricing-related
    is_pricing_query = any(keyword in question_lower for keyword in PRICING_KEYWORDS)

    if not is_pricing_query:
        return []

    # Determine which product pricing tables to inject
    tables_to_inject = set()

    for product_keyword, table_titles in PRODUCT_KEYWORDS.items():
        if product_keyword in question_lower:
            tables_to_inject.update(table_titles)

    # If no specific product mentioned but pricing query, use smart defaults
    if not tables_to_inject:
        # If asking about "instance types" specifically, include ALL pricing tables
        # since instance types exist for web services, databases, and cron jobs
        if 'instance type' in question_lower:
            tables_to_inject = {
                'Render Web Services Pricing',
                'Render Postgres Pricing',
                'Render Key Value Pricing',
                'Render Cron Jobs Pricing'
            }
        else:
            # For other generic pricing questions, default to databases
            tables_to_inject = {'Render Postgres Pricing', 'Render Key Value Pricing'}

    return list(tables_to_inject)


def _apply_relative_cutoff(documents: List[Document]) -> List[Document]:
    """Keep only docs competitive with the best retrieved match.

    A fixed absolute threshold can't tell a strong topic (best cosine ~0.65) from a
    weak one (best ~0.45) — at a low floor it lets a long tail of marginally-relevant
    docs through on broad questions. Anchoring the cutoff to the top match self-tunes:
    strong topics gate high and shed their tail, weak-but-valid topics keep their cluster.

    Anchors on the highest cosine in the set (not documents[0] — hybrid_search orders by
    RRF, so position 0 isn't guaranteed to be the top cosine) and drops anything below
    relevance_cutoff_fraction * top, with similarity_threshold as a hard floor. Returns
    survivors sorted by cosine desc so the weakest sit at the tail (lets the injection
    cap drop true-lowest-cosine docs).
    """
    if not documents:
        return documents

    top = max(doc.similarity_score for doc in documents)
    cutoff = max(settings.similarity_threshold, top * settings.relevance_cutoff_fraction)
    kept = sorted(
        (doc for doc in documents if doc.similarity_score >= cutoff),
        key=lambda doc: doc.similarity_score,
        reverse=True,
    )
    logfire.info(
        "Applied adaptive relevance cutoff",
        top=top,
        cutoff=cutoff,
        before=len(documents),
        after=len(kept),
    )
    return kept


async def inject_curated_docs(question: str, existing_docs: List[Document]) -> List[Document]:
    """
    Ensure the canonical doc for a matched topic is present — without padding the count.

    Data-driven replacement for the old per-topic detect_*/inject_* pairs: every rule
    (plus pricing's product logic) funnels through one fetch → parse → build path.

    Policy (replace-weakest, never grow past rag_top_k):
      - If a topic's curated doc was already retrieved, leave it — retrieval found it.
      - Otherwise insert it at the top (INJECTED_DOC_SCORE); if that pushes the set over
        the rag_top_k ceiling, drop the lowest-ranked retrieved doc from the tail.
    So curated docs are guaranteed-present and top-ranked, but the result count still
    reflects retrieval's relevance gate rather than always sitting at the cap + 1.
    """
    question_lower = question.lower()

    # Collect the lookups every matching rule wants, in declaration order.
    lookups: List[DocLookup] = []
    for rule in INJECTION_RULES:
        if _matches(question_lower, rule.keywords, rule.word_keywords):
            logfire.info(f"Curated-doc rule matched: {rule.name}")
            lookups.extend(rule.lookups)

    # Pricing keeps its own product → table logic but shares this fetch path.
    for title in detect_pricing_query(question):
        lookups.append(DocLookup(title=title))

    if not lookups:
        return existing_docs

    # De-dup lookups (e.g. pricing defaults could request the same table twice),
    # preserving order.
    seen_keys = set()
    unique_lookups: List[DocLookup] = []
    for lookup in lookups:
        key = (lookup.source, lookup.title)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_lookups.append(lookup)

    # Don't re-inject content already in the retrieved set. Chunks of one curated
    # page share a title, so dedup on (source, content) rather than (source, title).
    existing_keys = {(doc.source, doc.content) for doc in existing_docs}

    injected: List[Document] = []
    seen_keys: set = set()
    async with vector_store.pool.acquire() as conn:
        for lookup in unique_lookups:
            docs = await _fetch_curated_docs(conn, lookup)
            if not docs:
                logfire.warning(
                    "Curated doc not found in DB — run the matching ingest_source task",
                    source=lookup.source,
                    title=lookup.title,
                )
                continue
            for doc in docs:
                key = (doc.source, doc.content)
                if key in existing_keys or key in seen_keys:
                    continue
                seen_keys.add(key)
                injected.append(doc)

    if not injected:
        return existing_docs

    # Insert curated docs at the top; cap at the rag_top_k ceiling, dropping the
    # lowest-ranked retrieved docs from the tail (existing_docs is already in rank
    # order, so the tail is the weakest).
    combined = injected + existing_docs
    dropped = max(0, len(combined) - settings.rag_top_k)
    if dropped:
        combined = combined[:settings.rag_top_k]
    logfire.info(
        "Injected curated docs (replace-weakest)",
        injected=len(injected),
        dropped_to_fit=dropped,
        total_docs=len(combined),
    )
    return combined


@instrument_stage(PipelineConfig.STAGE_RETRIEVAL)
async def retrieve_documents(embedding: List[float], original_question: str = None) -> dict:
    """
    Find relevant documentation chunks via vector similarity.

    Uses multi-query retrieval for broad questions to ensure diverse coverage
    across multiple products/aspects.

    Args:
        embedding: Query embedding vector (used for fallback)
        original_question: Original question text (for query expansion)

    Returns:
        dict with 'documents', 'avg_similarity', 'cost_usd'
    """

    total_cost = 0.0001  # Base database query cost

    # Check if we should use multi-query retrieval
    if original_question and await should_expand_query(original_question):
        logfire.info(
            "Using multi-query retrieval for broad question",
            question_length=len(original_question),
            rag_top_k=settings.rag_top_k
        )

        # Expand query
        query_variations, expansion_cost = await expand_query(original_question)
        total_cost += expansion_cost

        logfire.info(
            "Expanded query to multiple variations",
            num_queries=len(query_variations),
            queries=query_variations,
            expansion_cost_usd=expansion_cost
        )

        # Retrieve documents for each query variation
        all_docs = {}            # content hash -> Document (highest cosine kept)
        original_hashes = set()  # content hashes that matched the original question

        # Calculate how many docs to retrieve per query
        # Target: ~30-40 total docs before dedup, then take top 20
        docs_per_query = max(10, settings.rag_top_k // len(query_variations) + 5)

        async def _embed_and_search(i: int, query: str):
            embed_result = await embed_question(query)
            docs = await vector_store.hybrid_search(
                query_text=query,
                query_embedding=embed_result["embedding"],
                k=docs_per_query,
                threshold=settings.similarity_threshold,
                bm25_weight=0.4  # 60% semantic, 40% BM25
            )
            return i, embed_result["cost_usd"], docs

        query_results = await asyncio.gather(*[
            _embed_and_search(i, query) for i, query in enumerate(query_variations)
        ])

        for i, cost, docs in query_results:
            logfire.debug(f"Retrieved {len(docs)} docs for query {i+1}/{len(query_variations)}")
            total_cost += cost

            # Deduplicate across variations: keep the highest cosine similarity seen
            # for each piece of content. (query_expansion.py places the original
            # question at index 0, the expanded variations after it.)
            for doc in docs:
                # Use first 200 chars as content hash
                content_hash = hash(doc.content[:200])
                if i == 0:
                    original_hashes.add(content_hash)

                if content_hash not in all_docs or doc.similarity_score > all_docs[content_hash].similarity_score:
                    all_docs[content_hash] = doc

        # Order by cosine similarity; on ties, prefer docs that matched the original
        # question over those found only by an expanded variation. (No score mutation —
        # the per-variation hybrid_search already gated each result by threshold.)
        ranked = sorted(
            all_docs.items(),
            key=lambda kv: (kv[1].similarity_score, kv[0] in original_hashes),
            reverse=True,
        )
        documents = [doc for _, doc in ranked][:settings.rag_top_k]

        logfire.info(
            "Multi-query retrieval completed",
            num_queries=len(query_variations),
            total_docs_before_dedup=len(all_docs),
            final_docs=len(documents)
        )
    else:
        # Single query retrieval with hybrid search (semantic + BM25)
        logfire.info("Using hybrid search (semantic + BM25)")

        documents = await vector_store.hybrid_search(
            query_text=original_question or "",
            query_embedding=embedding,
            k=settings.rag_top_k,
            threshold=settings.similarity_threshold,
            bm25_weight=0.4  # 60% semantic, 40% BM25 - favors semantic but includes keyword matches
        )

    # Adaptive relevance cutoff: drop the long tail of marginally-relevant docs by
    # keeping only those competitive with the best match. Applied BEFORE injection so
    # the curated docs (pinned at INJECTED_DOC_SCORE=1.0) don't poison the anchor.
    documents = _apply_relative_cutoff(documents)

    # Curated-doc injection (replace-weakest): ensure the canonical doc for a matched
    # topic is present and top-ranked, without padding the count past rag_top_k.
    # Data-driven — see INJECTION_RULES / inject_curated_docs.
    if original_question:
        documents = await inject_curated_docs(original_question, documents)

    # Calculate average similarity
    avg_similarity = 0.0
    if documents:
        avg_similarity = sum(doc.similarity_score for doc in documents) / len(documents)

    logfire.info(
        "Documents retrieved",
        count=len(documents),
        avg_similarity=avg_similarity,
        top_score=documents[0].similarity_score if documents else 0.0
    )

    return {
        "documents": documents,
        "avg_similarity": avg_similarity,
        "cost_usd": total_cost
    }
