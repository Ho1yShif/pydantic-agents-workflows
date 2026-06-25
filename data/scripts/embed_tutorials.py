"""Embed render.com/tutorials and merge them into the corpus JSON.

This is the incremental counterpart to generate_embeddings.py: instead of
re-embedding the entire corpus, it crawls only the Tutorials section, embeds those
chunks, and merges them into data/embeddings/render_docs.json (replacing any prior
tutorial entries so re-runs stay idempotent). Existing non-tutorial docs are left
untouched, keeping the committed diff small.

Run after the bulk corpus already exists:
    uv run python data/scripts/embed_tutorials.py

Then load into the database with:
    uv run python data/scripts/ingest_docs.py --sync
"""

import asyncio
import json
from pathlib import Path

from crawl_tutorials import fetch_tutorial_docs
from generate_embeddings import generate_embedding, validate_api_keys

TUTORIAL_SOURCE_PREFIX = "https://render.com/tutorials/"
EMBEDDINGS_PATH = Path(__file__).parent.parent / "embeddings" / "render_docs.json"


async def main() -> None:
    print("🚀 Embedding render.com/tutorials into the corpus")
    print("=" * 60)

    if not validate_api_keys():
        return

    if not EMBEDDINGS_PATH.exists():
        print(f"\n❌ {EMBEDDINGS_PATH} not found.")
        print("   Run generate_embeddings.py first to build the base corpus.")
        return

    with open(EMBEDDINGS_PATH) as f:
        corpus = json.load(f)

    before = len(corpus)
    # Drop any existing tutorial docs so this run fully refreshes them.
    corpus = [d for d in corpus if not d.get("source", "").startswith(TUTORIAL_SOURCE_PREFIX)]
    removed = before - len(corpus)
    print(f"\n📄 Loaded corpus: {before} docs ({removed} prior tutorial docs removed)")

    print("\n📚 Crawling tutorials...")
    tutorial_docs = await fetch_tutorial_docs()
    print(f"\n🔄 Embedding {len(tutorial_docs)} tutorial chunks...\n")

    embedded = []
    for i, doc in enumerate(tutorial_docs, 1):
        title = doc["title"][:60] + "..." if len(doc["title"]) > 60 else doc["title"]
        print(f"  [{i:3d}/{len(tutorial_docs)}] {title}")
        doc["embedding"] = await generate_embedding(doc["content"])
        embedded.append(doc)
        await asyncio.sleep(0.65)  # stay under the OpenAI rate limit

    corpus.extend(embedded)

    with open(EMBEDDINGS_PATH, "w") as f:
        json.dump(corpus, f, indent=2)

    print("\n" + "=" * 60)
    print("✅ SUCCESS!")
    print(f"📊 Corpus now has {len(corpus)} docs ({len(embedded)} tutorial chunks)")
    print(f"📁 Saved to: {EMBEDDINGS_PATH}")
    print("\n🎯 Next step: uv run python data/scripts/ingest_docs.py --sync")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
