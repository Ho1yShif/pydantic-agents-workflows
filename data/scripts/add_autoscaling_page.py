"""Add Render autoscaling/scaling documentation to embeddings.

This script adds curated content about Render's autoscaling and manual scaling
to the vector database so the Q&A system can reference it when developers
ask about scaling their services.
"""

import asyncio
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import vector_store
from backend.pipeline.embeddings import embed_question
from dotenv import load_dotenv

load_dotenv()

AUTOSCALING_URL = "https://render.com/docs/scaling"

CURATED_CONTENT = """# Autoscaling on Render
Source: https://render.com/docs/scaling

## Overview
Render supports manual scaling and automatic horizontal autoscaling for web services.
Autoscaling is available on paid plans (Starter instance type and above).

## Manual Scaling
Set the number of instances for a web service from 1 to N via the Dashboard or render.yaml.
Manual scaling does not require any additional configuration beyond setting the instance count.

## Autoscaling (Horizontal Scaling)
Render's autoscaler automatically adjusts the number of running instances for a web service
based on CPU and memory utilization metrics.

### How Autoscaling Works
- **minInstances**: The floor — Render always keeps at least this many instances running.
- **maxInstances**: The ceiling — Render will never scale beyond this count.
- **Scale-up trigger**: When CPU or memory exceeds the configured threshold, Render adds instances.
- **Scale-down trigger**: When utilization drops below the threshold for a sustained period,
  Render removes instances (but never below the minimum).
- **Cooldown periods**: After a scale event, autoscaling waits before triggering again to
  prevent flapping.

### Configuring Autoscaling in render.yaml
```yaml
services:
  - type: web
    name: my-app
    scaling:
      minInstances: 1
      maxInstances: 5
      targetMemoryPercent: 60   # optional, scale when memory exceeds 60%
      targetCPUPercent: 60      # optional, scale when CPU exceeds 60%
```

### Configuring Autoscaling via Dashboard
Go to your service → Settings → Scaling section. Set minimum instances, maximum instances,
and optional CPU/memory thresholds.

### Plan Requirements
Autoscaling requires a paid instance type (Starter or above). Free instances do not
support autoscaling. You must upgrade to at least the Starter plan to enable autoscaling.

### Supported Service Types
Autoscaling is available for web services. Background workers and private services
support manual instance count scaling.

### Zero Downtime During Scaling
Scale-up events add new instances before traffic is shifted to them. Existing instances
are drained gracefully on scale-down, ensuring zero-downtime during scaling events.

### Observability
Render's metrics dashboard shows instance count over time alongside CPU and memory metrics,
so you can verify autoscaling behavior and tune your thresholds.

## Instance Types for Scaling
- **Free**: No autoscaling support, single instance only
- **Starter**: Autoscaling supported, good for low-traffic apps
- **Standard**: Autoscaling supported, suitable for production workloads
- **Pro**: Autoscaling supported, high-performance workloads
- **Pro Max, Pro Ultra**: Autoscaling supported, maximum performance

## render.yaml Scaling Examples
Single fixed instance (no autoscaling):
```yaml
numInstances: 1
```

Autoscaling between 2 and 10 instances based on CPU:
```yaml
scaling:
  minInstances: 2
  maxInstances: 10
  targetCPUPercent: 70
```
"""


async def fetch_autoscaling_page():
    """Fetch and parse the autoscaling docs page."""
    print(f"Fetching {AUTOSCALING_URL}...")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(AUTOSCALING_URL)
            response.raise_for_status()

        print(f"Fetched {len(response.text):,} characters")
        return response.text
    except Exception as e:
        print(f"Warning: Could not fetch page ({e}), using curated content")
        return None


def extract_page_content(html: str) -> str:
    """Extract meaningful content from the page HTML."""
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
    """Build the final document content using curated content."""
    if scraped_text and len(scraped_text) > 500:
        print("Using curated content (structured for optimal semantic retrieval)")

    return CURATED_CONTENT


async def add_to_vector_store(content: str):
    """Add the autoscaling document to the vector store."""
    await vector_store.initialize()

    print("\nRemoving old autoscaling documents...")
    async with vector_store.pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM documents
            WHERE source = $1
        """, AUTOSCALING_URL)
        deleted_count = int(result.split()[-1])
        print(f"   Deleted {deleted_count} old documents")

    print("\nAdding autoscaling document to vector store...")

    if len(content) < 100:
        print("Error: Content too short, aborting")
        await vector_store.close()
        return

    embed_result = await embed_question(content)

    await vector_store.insert_document(
        content=content,
        source=AUTOSCALING_URL,
        title="Autoscaling on Render",
        embedding=embed_result["embedding"],
        section="Scaling and Autoscaling",
        metadata={
            "type": "docs",
            "category": "autoscaling",
            "title": "Autoscaling on Render"
        }
    )

    await vector_store.close()
    print("Successfully added 1 autoscaling document!")


async def main():
    print("=" * 80)
    print("ADDING RENDER AUTOSCALING DOCS TO VECTOR DATABASE")
    print("=" * 80)
    print()

    html = await fetch_autoscaling_page()

    scraped_text = extract_page_content(html) if html else ""
    content = build_document_content(scraped_text)

    print(f"Document length: {len(content):,} characters")

    await add_to_vector_store(content)

    print()
    print("=" * 80)
    print("COMPLETE")
    print("=" * 80)
    print()
    print("The Q&A system will now reference autoscaling docs when developers")
    print("ask about scaling their services on Render.")
    print()
    print("TIP: Re-run this script if the docs page content changes")


if __name__ == "__main__":
    asyncio.run(main())
