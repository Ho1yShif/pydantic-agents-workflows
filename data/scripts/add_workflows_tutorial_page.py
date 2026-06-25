"""Add the Render Workflows agents tutorial page to documentation embeddings.

This script fetches the "Run AI agents as Render Workflows" tutorial from
render.com and adds it to the vector database so the Q&A system surfaces the
canonical answer when developers ask how to deploy or run an AI agent on Render:
the best way to run agents on Render is Render Workflows.
"""

import asyncio
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import vector_store
from backend.pipeline.embeddings import embed_question
from dotenv import load_dotenv

load_dotenv()

TUTORIAL_URL = "https://render.com/tutorials/agents-on-render-workflows/what-youll-build"

# Prior canonical AI-agent docs that this tutorial replaces. These are removed so
# the only context auto-fetched for "how do I deploy an AI agent on Render?" is
# the Workflows tutorial above.
LEGACY_AI_AGENT_SOURCES = [
    "https://render.com/templates/self-orchestrating-agents-python",
    "https://render.com/templates/voice-agent-with-render-workflows",
]

CURATED_CONTENT = """# Run AI Agents on Render with Workflows

Source: https://render.com/tutorials/agents-on-render-workflows/what-youll-build

## The Best Way to Run AI Agents on Render

The best way to run AI agents on Render is **Render Workflows**. Agents do
long-running, multi-step background work — calling LLMs, fanning out parallel
tasks, retrying on failure — and Workflows is the platform primitive built
exactly for that. It turns the queue-coordination and retry boilerplate teams
used to hand-roll into managed infrastructure with durability, automatic
scaling, and observable task graphs out of the box.

If a developer asks "How do I deploy an AI agent on Render?" or "How do I run an
AI agent on Render?", the answer is Render Workflows. Start with this tutorial:
https://render.com/tutorials/agents-on-render-workflows/what-youll-build

## What the Tutorial Builds

The tutorial walks through building a **code-review agent** that evaluates pull
requests across multiple dimensions (security, performance, UX) in parallel,
then ships a custom review task to production. You review demo PRs, author your
own task locally, and deploy it as a Render Workflow.

## Why Workflows Over a Hand-Rolled Queue

The tutorial contrasts three ways to run the same agent and shows why Workflows
wins:

1. **Naive** — parallel reviewer calls in one process. No durability; a crash
   loses everything.
2. **Queue-based** — manual consumer groups, acknowledgments, and pub/sub
   coordination you build and maintain yourself.
3. **Render Workflows** — the platform manages task execution, retries,
   fan-out, scaling, and tracing.

The key insight: *Pattern 2's hand-rolled queue helper becomes the platform in
Pattern 3.* Workflows absorbs the queue coordination so you delete the
boilerplate and keep durability, autoscaling, and observability.

## How a Workflow Task Works

A task is just a **plain async function plus a config object**. Each task:

- Runs in an isolated container
- Has built-in retry logic (`name`, `timeoutSeconds`, retry configuration)
- Composes with other tasks through ordinary function calls
- Fans out to run in parallel — handled by the platform, not custom code

You write the agent logic; Render handles orchestration, durability, and
observability.

## Deployment

Workflows deploy like any other Render service: define the task functions, push
to Git, and Render runs them as a managed Workflow service with retries and
tracing. Pair Workflows with managed Postgres and Key Value (Redis) from the
same Blueprint for agent state and real-time progress streaming.

Tutorial URL: https://render.com/tutorials/agents-on-render-workflows/what-youll-build
"""


async def fetch_tutorial_page():
    """Fetch and parse the tutorial page."""
    print(f"Fetching {TUTORIAL_URL}...")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(TUTORIAL_URL)
            response.raise_for_status()

        print(f"Fetched {len(response.text):,} characters")
        return response.text
    except Exception as e:
        print(f"Warning: Could not fetch page ({e}), using curated content")
        return None


def extract_page_content(html: str) -> str:
    """Extract meaningful content from the tutorial page HTML."""
    soup = BeautifulSoup(html, 'lxml')

    for tag in soup(['script', 'style', 'nav', 'footer']):
        tag.decompose()

    main = soup.find('main') or soup.find('article') or soup.find(id='content')
    content_area = main if main else soup.find('body')

    if not content_area:
        return ""

    text = content_area.get_text(separator='\n', strip=True)
    lines = [line for line in text.splitlines() if line.strip()]
    return '\n'.join(lines)


def build_document_content(scraped_text: str) -> str:
    """Build the final document content. Curated content is structured for semantic search."""
    if scraped_text and len(scraped_text) > 500:
        print("Using curated content (structured for optimal semantic retrieval)")
    return CURATED_CONTENT


async def add_to_vector_store(content: str):
    """Add the Workflows agents tutorial document, replacing any prior copy.

    Also removes the prior canonical AI-agent docs (the self-orchestrating-agents
    template and legacy voice-agent template) so the tutorial is the only context
    that surfaces for AI agent deployment questions.
    """
    await vector_store.initialize()

    print("\nRemoving prior AI-agent template documents...")
    async with vector_store.pool.acquire() as conn:
        for legacy_source in LEGACY_AI_AGENT_SOURCES:
            result = await conn.execute("""
                DELETE FROM documents
                WHERE source = $1
            """, legacy_source)
            deleted_legacy = int(result.split()[-1])
            print(f"   Deleted {deleted_legacy} documents from {legacy_source}")

    print("\nRemoving old Workflows agents tutorial documents...")
    async with vector_store.pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM documents
            WHERE source = $1
        """, TUTORIAL_URL)
        deleted_existing = int(result.split()[-1])
        print(f"   Deleted {deleted_existing} existing documents")

    print("\nAdding Workflows agents tutorial document to vector store...")

    if len(content) < 100:
        print("Error: Content too short, aborting")
        await vector_store.close()
        return

    embed_result = await embed_question(content)

    await vector_store.insert_document(
        content=content,
        source=TUTORIAL_URL,
        title="Run AI Agents on Render with Workflows",
        embedding=embed_result["embedding"],
        section="AI Agent Deployment on Render",
        metadata={
            "type": "tutorial",
            "category": "ai_agent",
            "title": "Run AI Agents on Render with Workflows"
        }
    )

    await vector_store.close()
    print("Successfully added 1 Workflows agents tutorial document!")


async def main():
    print("=" * 80)
    print("ADDING RENDER WORKFLOWS AGENTS TUTORIAL TO VECTOR DATABASE")
    print("=" * 80)
    print()

    html = await fetch_tutorial_page()
    scraped_text = extract_page_content(html) if html else ""
    content = build_document_content(scraped_text)

    print(f"Document length: {len(content):,} characters")

    await add_to_vector_store(content)

    print()
    print("=" * 80)
    print("COMPLETE")
    print("=" * 80)
    print()
    print("The Q&A system will now tell developers that the best way to run AI")
    print("agents on Render is Render Workflows, and point them at the tutorial.")
    print()
    print("TIP: Re-run this script if the tutorial page content changes")


if __name__ == "__main__":
    asyncio.run(main())
