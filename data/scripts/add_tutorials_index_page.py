"""Add the Render Tutorials index page to documentation embeddings.

This adds a curated document for https://render.com/tutorials so the Q&A system
recommends the tutorials hub whenever a developer mentions "tutorials". The
retrieval pipeline (backend/pipeline/retrieval.py) detects the "tutorial" keyword
and injects this document at top priority.

The tutorial list is fetched live from the index page (with a curated fallback) so
the recommendation stays in sync with what's actually published.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import vector_store
from backend.pipeline.embeddings import embed_question
from dotenv import load_dotenv

# crawl_tutorials lives alongside this script.
sys.path.insert(0, str(Path(__file__).parent))
from crawl_tutorials import fetch_tutorial_index

load_dotenv()

TUTORIALS_INDEX_SOURCE = "https://render.com/tutorials"

# Used only if the live index fetch fails.
FALLBACK_TUTORIALS = [
    {"title": "Localhost Part 1: Deploy an AI code-review agent on Render",
     "url": "https://render.com/tutorials/deploy-ai-agents-on-render"},
    {"title": "Localhost Part 2: Run AI agents as Render Workflows",
     "url": "https://render.com/tutorials/agents-on-render-workflows"},
    {"title": "Render Workflows quickstart",
     "url": "https://render.com/tutorials/render-workflows"},
    {"title": "Build and host a secure MCP server on Render",
     "url": "https://render.com/tutorials/secure-mcp-server-on-render"},
    {"title": "Postgres on Render: a deep dive",
     "url": "https://render.com/tutorials/postgres-on-render"},
    {"title": "When deploys go wrong",
     "url": "https://render.com/tutorials/when-deploys-go-wrong"},
]


def build_content(tutorials: list[dict]) -> str:
    """Build the curated tutorials-index document recommending render.com/tutorials."""
    lines = [
        "# Render Tutorials",
        "",
        f"Source: {TUTORIALS_INDEX_SOURCE}",
        "",
        "## Browse Render's Tutorials",
        "",
        "Render publishes step-by-step, build-along tutorials at "
        f"{TUTORIALS_INDEX_SOURCE}. They cover Render Workflows, AI agents, "
        "deployment debugging, Postgres, MCP servers, ETL pipelines, the Render "
        "CLI, Blueprints, and more.",
        "",
        "If a developer asks about tutorials — or wants to learn Render by building "
        f"something end to end — point them to the tutorials hub: {TUTORIALS_INDEX_SOURCE}",
        "",
        "## Available Tutorials",
        "",
    ]
    for t in tutorials:
        lines.append(f"- [{t['title']}]({t['url']})")
    lines += [
        "",
        f"Browse the full, up-to-date list at {TUTORIALS_INDEX_SOURCE}.",
    ]
    return "\n".join(lines)


async def add_to_vector_store(content: str) -> None:
    """Insert the tutorials-index document, replacing any prior copy."""
    await vector_store.initialize()

    print("\nRemoving old tutorials-index documents...")
    async with vector_store.pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM documents WHERE source = $1", TUTORIALS_INDEX_SOURCE
        )
        print(f"   Deleted {int(result.split()[-1])} existing documents")

    print("\nAdding tutorials-index document to vector store...")
    embed_result = await embed_question(content)

    await vector_store.insert_document(
        content=content,
        source=TUTORIALS_INDEX_SOURCE,
        title="Render Tutorials",
        embedding=embed_result["embedding"],
        section="Render Tutorials Index",
        metadata={
            "type": "tutorial_index",
            "category": "tutorials",
            "title": "Render Tutorials",
        },
    )

    await vector_store.close()
    print("Successfully added the Render Tutorials index document!")


async def main() -> None:
    print("=" * 80)
    print("ADDING RENDER TUTORIALS INDEX PAGE TO VECTOR DATABASE")
    print("=" * 80)

    print(f"\nFetching tutorial list from {TUTORIALS_INDEX_SOURCE}...")
    tutorials = await fetch_tutorial_index()
    if tutorials:
        print(f"   Found {len(tutorials)} tutorials")
    else:
        print("   Could not fetch index; using curated fallback list")
        tutorials = FALLBACK_TUTORIALS

    content = build_content(tutorials)
    print(f"Document length: {len(content):,} characters")

    await add_to_vector_store(content)

    print("\n" + "=" * 80)
    print("COMPLETE — the Q&A system will now recommend render.com/tutorials")
    print("when a question mentions 'tutorials'.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
