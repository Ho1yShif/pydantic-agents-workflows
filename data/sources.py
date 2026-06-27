"""Declarative registry of live RAG sources.

Each :class:`Source` knows how to *build* its documents — the only part that
varies between sources. Embedding and the delete-by-source upsert are handled
uniformly by :mod:`backend.ingestion`. This registry replaces the six
near-identical ``data/scripts/add_*_page.py`` scripts: adding a source is now a
registry entry (plus, for curated pages, a markdown file in ``data/curated/``),
not a new script.

Three build strategies cover every live source:

* **curated page** — content is a hand-maintained markdown file in
  ``data/curated/<name>.md`` (autoscaling, nodejs, workflows_docs,
  workflows_tutorial).
* **table parse** — scrape and format the pricing tables (pricing).
* **nav list** — build a recommendation doc from the live tutorials index
  (tutorials_index).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from bs4 import BeautifulSoup

# crawl_tutorials / chunking live in data/scripts, so put that directory on the
# path before importing from them.
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from chunking import chunk_document  # noqa: E402
from crawl_tutorials import fetch_tutorial_index  # noqa: E402

Doc = dict[str, Any]

CURATED_DIR = Path(__file__).parent / "curated"


@dataclass(frozen=True)
class Source:
    """A live documentation source ingested into the vector store."""

    name: str                                   # registry key + ingest_source() input
    source_url: str                             # canonical `source` value (delete key + dedup)
    build: Callable[[], Awaitable[list[Doc]]]   # fetch/parse → docs (pre-embedding)
    legacy_sources: tuple[str, ...] = ()        # extra sources this one supersedes


# ---------------------------------------------------------------------------
# Strategy 1: curated page — chunked docs from data/curated/<name>.md
# ---------------------------------------------------------------------------

def _curated_build(
    name: str, source_url: str, title: str, section: str, metadata: dict
) -> Callable[[], Awaitable[list[Doc]]]:
    """Build chunked docs from the curated markdown file ``data/curated/<name>.md``.

    The content is split with the same ``chunk_document`` utility the bulk corpus
    and tutorials crawl use, so each fact gets its own focused embedding. (A single
    monolithic embedding per page made specific claims fail verification — they
    couldn't surface the whole-page blob in a top-5 similarity search.)

    The curated content is hand-structured for semantic retrieval, so (unlike the
    old scripts) we don't make a throwaway live fetch — the result was always
    discarded in favor of the curated text anyway.
    """

    async def build() -> list[Doc]:
        content = (CURATED_DIR / f"{name}.md").read_text(encoding="utf-8")
        return [
            {
                "content": chunk["content"],
                "title": chunk["title"],
                "section": chunk["section"],
                "metadata": metadata,
            }
            for chunk in chunk_document(title, section, source_url, content)
        ]

    return build


# ---------------------------------------------------------------------------
# Strategy 2: pricing — scrape and format the live pricing tables
# ---------------------------------------------------------------------------

PRICING_URL = "https://render.com/pricing"


def _extract_table_data(table) -> tuple[list[str], list[list[str]]]:
    """Extract headers and body rows from an HTML table element."""
    headers: list[str] = []
    header_row = table.find("thead")
    if header_row:
        for th in header_row.find_all(["th", "td"]):
            headers.append(th.get_text(strip=True))

    rows: list[list[str]] = []
    body = table.find("tbody")
    if body:
        for tr in body.find_all("tr"):
            row = []
            for td in tr.find_all(["td", "th"]):
                text = " ".join(td.get_text(strip=True).split())
                row.append(text)
            if row:
                rows.append(row)

    return headers, rows


def _format_table_as_text(headers: list[str], rows: list[list[str]], title: str) -> str | None:
    """Format table data as readable text with context for better semantic matching."""
    if not rows:
        return None

    lines = [f"# {title}", "Source: https://render.com/pricing", ""]

    if "Web Services" in title:
        lines.append("This table shows all available instance types, pricing plans, and tiers for Render Web Services, Private Services, and Background Workers.")
        lines.append("Plans range from Free to Pro Ultra with specifications for RAM, CPU, and monthly costs.")
        lines.append("")
    elif "Postgres" in title:
        lines.append("This table shows all available database plans, instance types, tiers, and pricing for Render Postgres databases.")
        lines.append("Plans include Free, Basic, Pro, and Accelerated tiers with specifications for CPU, RAM, storage, and connection limits.")
        lines.append("Database plans range from free tier to large production instances.")
        lines.append("")
    elif "Key Value" in title:
        lines.append("This table shows all available datastore plans, instance types, tiers, and pricing for Render Key Value (Redis-compatible).")
        lines.append("Plans include Free, Starter, Standard, Pro, and Pro Plus with specifications for RAM, connection limits, and persistence options.")
        lines.append("Key Value database plans range from free tier to large production instances.")
        lines.append("")
    elif "Cron" in title:
        lines.append("This table shows all available instance types and pricing for Render Cron Jobs.")
        lines.append("Pricing is per-minute based on RAM and CPU specifications.")
        lines.append("")

    if headers:
        lines.append(" | ".join(headers))
        lines.append(" | ".join(["-" * len(h) for h in headers]))

    for row in rows:
        lines.append(" | ".join(row))

    return "\n".join(lines)


def _pricing_table_title(table, index: int) -> str:
    """Determine a descriptive title for a pricing table from its content."""
    table_text = table.get_text().lower()

    if "postgres" in table_text or "accelerated" in table_text or "basic-" in table_text:
        return "Render Postgres Pricing"
    if "key value" in table_text or ("starter" in table_text and "connection limit" in table_text):
        return "Render Key Value Pricing"
    if "cron" in table_text or "/minute" in table_text:
        return "Render Cron Jobs Pricing"
    if "web service" in table_text or "pro max" in table_text or "pro ultra" in table_text:
        return "Render Web Services Pricing"

    prev_heading = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
    if prev_heading:
        return " ".join(prev_heading.get_text(strip=True).split())
    return f"Render Pricing Table {index}"


async def _build_pricing() -> list[Doc]:
    """Scrape render.com/pricing and emit one doc per pricing table."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(PRICING_URL)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    docs: list[Doc] = []
    for i, table in enumerate(soup.find_all("table"), 1):
        title = _pricing_table_title(table, i)
        headers, rows = _extract_table_data(table)
        if not rows:
            continue
        content = _format_table_as_text(headers, rows, title)
        if content:
            docs.append({
                "content": content,
                "title": title,
                "section": title,
                "metadata": {"type": "pricing", "title": title},
            })
    return docs


# ---------------------------------------------------------------------------
# Strategy 3: tutorials index — recommendation doc from the live index
# ---------------------------------------------------------------------------

TUTORIALS_INDEX_URL = "https://render.com/tutorials"

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


def _tutorials_index_content(tutorials: list[dict]) -> str:
    """Build the curated tutorials-index document recommending render.com/tutorials."""
    lines = [
        "# Render Tutorials",
        "",
        f"Source: {TUTORIALS_INDEX_URL}",
        "",
        "## Browse Render's Tutorials",
        "",
        "Render publishes step-by-step, build-along tutorials at "
        f"{TUTORIALS_INDEX_URL}. They cover Render Workflows, AI agents, "
        "deployment debugging, Postgres, MCP servers, ETL pipelines, the Render "
        "CLI, Blueprints, and more.",
        "",
        "If a developer asks about tutorials — or wants to learn Render by building "
        f"something end to end — point them to the tutorials hub: {TUTORIALS_INDEX_URL}",
        "",
        "## Available Tutorials",
        "",
    ]
    for t in tutorials:
        lines.append(f"- [{t['title']}]({t['url']})")
    lines += [
        "",
        f"Browse the full, up-to-date list at {TUTORIALS_INDEX_URL}.",
    ]
    return "\n".join(lines)


async def _build_tutorials_index() -> list[Doc]:
    """Fetch the live tutorial list (curated fallback) and build the nav doc."""
    tutorials = await fetch_tutorial_index() or FALLBACK_TUTORIALS
    return [{
        "content": _tutorials_index_content(tutorials),
        "title": "Render Tutorials",
        "section": "Render Tutorials Index",
        "metadata": {"type": "tutorial_index", "category": "tutorials", "title": "Render Tutorials"},
    }]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SOURCES: dict[str, Source] = {
    "pricing": Source(
        name="pricing",
        source_url=PRICING_URL,
        build=_build_pricing,
    ),
    "autoscaling": Source(
        name="autoscaling",
        source_url="https://render.com/docs/scaling",
        build=_curated_build(
            "autoscaling",
            source_url="https://render.com/docs/scaling",
            title="Autoscaling on Render",
            section="Scaling and Autoscaling",
            metadata={"type": "docs", "category": "autoscaling", "title": "Autoscaling on Render"},
        ),
    ),
    "nodejs": Source(
        name="nodejs",
        source_url="https://render.com/docs/deploy-node-express-app",
        build=_curated_build(
            "nodejs",
            source_url="https://render.com/docs/deploy-node-express-app",
            title="Deploying a Node.js App on Render",
            section="Node.js Deployment",
            metadata={"type": "docs", "category": "nodejs_deployment", "title": "Deploying a Node.js App on Render"},
        ),
    ),
    "workflows_docs": Source(
        name="workflows_docs",
        source_url="https://render.com/docs/workflows",
        build=_curated_build(
            "workflows_docs",
            source_url="https://render.com/docs/workflows",
            title="Render Workflows Documentation",
            section="AI Agent Deployment on Render",
            metadata={"type": "docs", "category": "ai_agent", "title": "Render Workflows Documentation"},
        ),
    ),
    "workflows_tutorial": Source(
        name="workflows_tutorial",
        source_url="https://render.com/tutorials/agents-on-render-workflows/what-youll-build",
        build=_curated_build(
            "workflows_tutorial",
            source_url="https://render.com/tutorials/agents-on-render-workflows/what-youll-build",
            title="Run AI Agents on Render with Workflows",
            section="AI Agent Deployment on Render",
            metadata={"type": "tutorial", "category": "ai_agent", "title": "Run AI Agents on Render with Workflows"},
        ),
        # Prior canonical AI-agent template docs this tutorial replaces, removed so
        # the only context surfaced for "how do I run an AI agent on Render?" is this.
        legacy_sources=(
            "https://render.com/templates/self-orchestrating-agents-python",
            "https://render.com/templates/voice-agent-with-render-workflows",
        ),
    ),
    "tutorials_index": Source(
        name="tutorials_index",
        source_url=TUTORIALS_INDEX_URL,
        build=_build_tutorials_index,
    ),
}
