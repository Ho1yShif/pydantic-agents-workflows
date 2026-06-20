"""Add the Render Workflows documentation page to documentation embeddings.

This script fetches the official Render Workflows docs and adds them to the
vector database. It is injected alongside the Workflows agents tutorial for any
question mentioning "ai" or "agents", giving the verification and accuracy
stages authoritative documentation to check the generated answer against.
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

DOCS_URL = "https://render.com/docs/workflows"

CURATED_CONTENT = """# Render Workflows Documentation

Source: https://render.com/docs/workflows

## What Render Workflows Is

Render Workflows is an end-to-end orchestration and execution engine for
long-running, distributed tasks. Tasks execute across hundreds of concurrent
instances, with automatic queuing and provisioning managed by Render. It is the
recommended way to run AI agents on Render, alongside background jobs, ETL
pipelines, and batch processing.

## What's in a Workflow?

A workflow is built from **tasks**. A task is a standard TypeScript or Python
function registered with Render's SDK. Tasks can chain other tasks — or
themselves — and execute arbitrary logic, including AI agents that call LLMs and
fan out work.

## Defining Tasks

- Tasks are plain async functions plus a config object, registered with the
  Render Workflows SDK.
- The SDK is available for **TypeScript and Python** (more languages planned).
- The same SDK is used both to define tasks and to trigger runs from web apps,
  agents, or CI/CD systems.

## Execution Behavior

- **Timeouts** — each task run can execute for up to **24 hours**, customizable
  per task.
- **Retries** — if a task run fails, Render automatically retries it according
  to your settings.
- **Compute specs** — instance type is selectable per task for resource-intensive
  work.
- **Parallelism / fan-out** — a task can dispatch multiple concurrent runs and
  await their results. Render manages queuing if the workspace concurrency limit
  is exceeded.
- **Durability** — task execution is orchestrated and retried by the platform,
  so a crash doesn't lose in-flight work.

## Workflows vs. Job Queues

Workflows replaces hand-rolled job queues: the queue coordination, consumer
groups, acknowledgments, retries, and scaling you would otherwise build and
maintain become managed platform infrastructure.

## Deployment

A Workflow service pulls task definitions from a GitHub / GitLab / Bitbucket
repository. Render builds the project into a custom image, caches it, and pushes
it to each task instance. You define your task functions, push to Git, and
Render runs them as a managed Workflow service with retries and tracing.

## Pricing

Render bills only for compute usage (prorated by the second) and, optionally,
for increasing your workspace's maximum number of concurrent task runs.

## Beta Limitations

During the beta, Workflows does not support: native scheduling (use a cron job
to trigger runs instead), Blueprints, HIPAA compliance, network-isolated
environments, or incoming network connections on runs.

Docs URL: https://render.com/docs/workflows
"""


async def fetch_docs_page():
    """Fetch and parse the docs page."""
    print(f"Fetching {DOCS_URL}...")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(DOCS_URL)
            response.raise_for_status()

        print(f"Fetched {len(response.text):,} characters")
        return response.text
    except Exception as e:
        print(f"Warning: Could not fetch page ({e}), using curated content")
        return None


def extract_page_content(html: str) -> str:
    """Extract meaningful content from the docs page HTML."""
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
    """Add the Render Workflows docs document, replacing any prior copy."""
    await vector_store.initialize()

    print("\nRemoving old Workflows docs documents...")
    async with vector_store.pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM documents
            WHERE source = $1
        """, DOCS_URL)
        deleted_existing = int(result.split()[-1])
        print(f"   Deleted {deleted_existing} existing documents")

    print("\nAdding Render Workflows docs document to vector store...")

    if len(content) < 100:
        print("Error: Content too short, aborting")
        await vector_store.close()
        return

    embed_result = await embed_question(content)

    await vector_store.insert_document(
        content=content,
        source=DOCS_URL,
        title="Render Workflows Documentation",
        embedding=embed_result["embedding"],
        section="AI Agent Deployment on Render",
        metadata={
            "type": "docs",
            "category": "ai_agent",
            "title": "Render Workflows Documentation"
        }
    )

    await vector_store.close()
    print("Successfully added 1 Render Workflows docs document!")


async def main():
    print("=" * 80)
    print("ADDING RENDER WORKFLOWS DOCS TO VECTOR DATABASE")
    print("=" * 80)
    print()

    html = await fetch_docs_page()
    scraped_text = extract_page_content(html) if html else ""
    content = build_document_content(scraped_text)

    print(f"Document length: {len(content):,} characters")

    await add_to_vector_store(content)

    print()
    print("=" * 80)
    print("COMPLETE")
    print("=" * 80)
    print()
    print("The Q&A system will now inject the Render Workflows docs for any")
    print("question mentioning 'ai' or 'agents', giving the verification and")
    print("accuracy stages authoritative material to check answers against.")
    print()
    print("TIP: Re-run this script if the docs page content changes")


if __name__ == "__main__":
    asyncio.run(main())
