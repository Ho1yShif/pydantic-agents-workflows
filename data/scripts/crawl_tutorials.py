"""Crawl the render.com/tutorials section into RAG-ready document chunks.

The Tutorials section is NOT included in render.com/docs/llms-full.txt (the bulk
corpus source), so without this crawl the Q&A system can't answer tutorial-specific
questions. This module enumerates every tutorial from the /tutorials index, follows
each tutorial's sub-page links one level deep (the substantive step-by-step content),
extracts the readable text, and chunks it into the same doc shape used by
generate_embeddings.py.

`fetch_tutorial_docs()` returns a list of {title, section, source, content} dicts.
generate_embeddings.py calls it and embeds the result alongside the bulk docs.

Run directly (`python data/scripts/crawl_tutorials.py`) to print the discovered
pages and chunk counts without generating embeddings.
"""

import asyncio
import re
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from chunking import chunk_document

BASE_URL = "https://render.com"
INDEX_URL = f"{BASE_URL}/tutorials"

# Already curated by the `workflows_tutorial` source (data/sources.py), which
# deletes-by-source and reinserts after ingest — crawling it here would just be
# overwritten.
EXCLUDE_SOURCES: Set[str] = {
    "https://render.com/tutorials/agents-on-render-workflows/what-youll-build",
}

# Low-value, non-instructional sub-pages to skip (matched against the final path segment).
SKIP_SLUGS: Set[str] = {
    "share-your-feedback",
}

# Match tutorial overview pages: /tutorials/<slug>
OVERVIEW_RE = re.compile(r"^/tutorials/[^/]+/?$")
# Match tutorial sub-pages: /tutorials/<slug>/<sub>
SUBPAGE_RE = re.compile(r"^/tutorials/[^/]+/[^/]+/?$")

REQUEST_TIMEOUT = 30
CONCURRENCY = 5


def _normalize_path(href: str) -> str:
    """Reduce an href to a clean absolute-path (strip query/fragment, trailing slash)."""
    parsed = urlparse(href)
    path = parsed.path.rstrip("/")
    return path or "/"


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:  # noqa: BLE001 - best-effort crawl, log and continue
        print(f"  ⚠️  Could not fetch {url} ({e})")
        return None


def _extract_links(html: str, predicate) -> Set[str]:
    """Return the set of normalized /tutorials/... paths whose path matches predicate."""
    soup = BeautifulSoup(html, "lxml")
    paths: Set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        # Only consider on-site tutorial links.
        if href.startswith("http"):
            if not href.startswith(BASE_URL):
                continue
            path = _normalize_path(href)
        elif href.startswith("/"):
            path = _normalize_path(href)
        else:
            continue
        if predicate(path):
            paths.add(path)
    return paths


def _extract_content(html: str) -> tuple[str, str]:
    """Extract (title, body_text) from a tutorial page."""
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    main = soup.find("main") or soup.find("article") or soup.find(id="content")
    content_area = main if main else soup.find("body")
    if not content_area:
        return title, ""

    text = content_area.get_text(separator="\n", strip=True)
    lines = [line for line in text.splitlines() if line.strip()]
    return title, "\n".join(lines)


async def _discover_pages(client: httpx.AsyncClient) -> List[str]:
    """Return the full list of tutorial page paths (overviews + sub-pages)."""
    print(f"📡 Fetching tutorials index {INDEX_URL}...")
    index_html = await _fetch(client, INDEX_URL)
    if not index_html:
        print("❌ Could not fetch the tutorials index; returning no tutorial docs.")
        return []

    overviews = sorted(_extract_links(index_html, OVERVIEW_RE.match))
    print(f"📄 Found {len(overviews)} tutorial overview pages")

    pages: Set[str] = set(overviews)

    async def collect_subpages(overview_path: str) -> None:
        slug = overview_path.split("/")[2]  # /tutorials/<slug>
        html = await _fetch(client, urljoin(BASE_URL, overview_path))
        if not html:
            return
        subpage_prefix = f"/tutorials/{slug}/"
        subpages = _extract_links(
            html,
            lambda p: SUBPAGE_RE.match(p) and p.startswith(subpage_prefix),
        )
        pages.update(subpages)

    sem = asyncio.Semaphore(CONCURRENCY)

    async def guarded(path: str) -> None:
        async with sem:
            await collect_subpages(path)

    await asyncio.gather(*(guarded(p) for p in overviews))

    # Apply exclusions / skips.
    result = []
    for path in sorted(pages):
        source = urljoin(BASE_URL, path)
        if source in EXCLUDE_SOURCES:
            continue
        if path.split("/")[-1] in SKIP_SLUGS:
            continue
        result.append(path)
    return result


async def fetch_tutorial_index() -> List[Dict]:
    """Return [{title, url}] for each tutorial overview linked from the index page."""
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        html = await _fetch(client, INDEX_URL)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    seen: Set[str] = set()
    tutorials: List[Dict] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith(BASE_URL):
            path = _normalize_path(href)
        elif href.startswith("/"):
            path = _normalize_path(href)
        else:
            continue
        if not OVERVIEW_RE.match(path) or path in seen:
            continue
        seen.add(path)
        title = anchor.get_text(strip=True)
        if not title:
            title = path.split("/")[-1].replace("-", " ").title()
        tutorials.append({"title": title, "url": urljoin(BASE_URL, path)})
    return tutorials


async def fetch_tutorial_docs() -> List[Dict]:
    """Crawl all tutorials + sub-pages and return chunked doc dicts."""
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=True
    ) as client:
        pages = await _discover_pages(client)
        print(f"🔎 Crawling {len(pages)} tutorial pages...")

        sem = asyncio.Semaphore(CONCURRENCY)

        async def crawl_page(path: str) -> List[Dict]:
            source = urljoin(BASE_URL, path)
            async with sem:
                html = await _fetch(client, source)
            if not html:
                return []
            title, body = _extract_content(html)
            if not title:
                # Fall back to a readable title from the slug.
                title = path.split("/")[-1].replace("-", " ").title()
            docs = chunk_document(
                title=title, section=None, source=source, content=body
            )
            if not docs:
                print(f"  ⚠️  Skipping {source} (insufficient content)")
            return docs

        results = await asyncio.gather(*(crawl_page(p) for p in pages))

    docs = [doc for page_docs in results for doc in page_docs]
    print(f"✅ Produced {len(docs)} tutorial chunks from {len(pages)} pages")
    return docs


async def _main() -> None:
    docs = await fetch_tutorial_docs()
    by_source: Dict[str, int] = {}
    for doc in docs:
        by_source[doc["source"]] = by_source.get(doc["source"], 0) + 1
    print("\n" + "=" * 70)
    print(f"Discovered {len(by_source)} tutorial pages, {len(docs)} total chunks:")
    print("=" * 70)
    for source in sorted(by_source):
        print(f"  {by_source[source]:3d} chunks  {source}")


if __name__ == "__main__":
    asyncio.run(_main())
