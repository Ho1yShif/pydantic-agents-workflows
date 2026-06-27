"""Local-dev CLI to ingest one or all live sources into the vector store.

Mirrors the ``ingest_source`` / ``ingest_all`` Workflow tasks (``workflows/app.py``)
for local use without going through Render Workflows — same registry, same shared
build → embed → replace-by-source helpers.

Usage:

    python data/scripts/ingest_pages.py            # all live sources
    python data/scripts/ingest_pages.py pricing    # one source
    python data/scripts/ingest_pages.py pricing nodejs   # several
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

from backend.database import vector_store
from backend.ingestion import embed_documents, replace_source
from data.sources import SOURCES

load_dotenv()


async def _ingest_one(name: str) -> None:
    src = SOURCES[name]
    docs = await embed_documents(await src.build())
    inserted = await replace_source(src.source_url, docs, legacy=src.legacy_sources)
    print(f"  {name}: inserted {inserted} document(s) for {src.source_url}")


async def main(names: list[str]) -> None:
    print(f"Ingesting live sources: {', '.join(names)}")
    await vector_store.initialize()
    try:
        for name in names:
            await _ingest_one(name)
    finally:
        await vector_store.close()
    print("Done.")


if __name__ == "__main__":
    requested = sys.argv[1:] or list(SOURCES)
    unknown = [n for n in requested if n not in SOURCES]
    if unknown:
        sys.exit(f"Unknown source(s): {unknown}. Available: {list(SOURCES)}")
    asyncio.run(main(requested))
