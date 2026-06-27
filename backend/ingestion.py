"""Shared helpers for ingesting live sources into the RAG vector store.

Every live source follows the same shape — *build* its documents, *embed* them,
then *replace* the source's rows transactionally. These two helpers centralize
the embed loop and the delete-by-source + insert block that used to be
copy-pasted across all six ``data/scripts/add_*_page.py`` files.

A "doc" is a plain dict produced by a source builder (see ``data/sources.py``):

    {"content": str, "title": str, "section": str | None, "metadata": dict}

``embed_documents`` adds an ``"embedding"`` key; ``replace_source`` writes the
embedded docs to the ``documents`` table.
"""

from __future__ import annotations

import asyncio
from typing import Any

import logfire

from backend.database import vector_store
from backend.pipeline.embeddings import embed_question

Doc = dict[str, Any]

# Docs shorter than this are skipped — too small to be useful (matches the
# per-script guard the old add_* scripts applied before inserting).
MIN_CONTENT_CHARS = 100

# Optional inter-embedding delay. 0 by default (the live sources embed only a
# handful of docs); raise it if a large source starts hitting OpenAI rate limits.
EMBED_DELAY_S = 0.0


async def embed_documents(docs: list[Doc]) -> list[Doc]:
    """Embed each doc's content, returning only the docs that were embedded.

    Docs below :data:`MIN_CONTENT_CHARS` are skipped. Reuses the same
    ``embed_question`` embedder used at query time, so ingestion and retrieval
    share one embedding code path.
    """
    embedded: list[Doc] = []
    for doc in docs:
        content = doc["content"]
        if len(content) < MIN_CONTENT_CHARS:
            logfire.warn(
                "Skipping doc (content too short)",
                title=doc.get("title"),
                chars=len(content),
            )
            continue
        result = await embed_question(content)
        embedded.append({**doc, "embedding": result["embedding"]})
        if EMBED_DELAY_S:
            await asyncio.sleep(EMBED_DELAY_S)
    return embedded


async def replace_source(
    source: str, docs: list[Doc], *, legacy: tuple[str, ...] = ()
) -> int:
    """Replace all rows for ``source`` (and any ``legacy`` sources) with ``docs``.

    Deletes existing rows for the canonical source plus any legacy sources it
    supersedes (one transaction), then inserts the embedded docs. Returns the
    number of docs inserted. Assumes the pgvector pool is already initialized
    (the workflow task does this via ``_ensure_ready(db=True)``).
    """
    async with vector_store.pool.acquire() as conn:
        async with conn.transaction():
            for src in (source, *legacy):
                result = await conn.execute(
                    "DELETE FROM documents WHERE source = $1", src
                )
                logfire.info(
                    "Cleared existing rows for source",
                    source=src,
                    deleted=int(result.split()[-1]),
                )

    inserted = 0
    for doc in docs:
        await vector_store.insert_document(
            content=doc["content"],
            source=source,
            title=doc["title"],
            embedding=doc["embedding"],
            section=doc.get("section"),
            metadata=doc.get("metadata") or {},
        )
        inserted += 1

    logfire.info("Inserted documents for source", source=source, inserted=inserted)
    return inserted
