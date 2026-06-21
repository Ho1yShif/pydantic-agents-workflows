"""Ingest pre-generated embeddings into PostgreSQL with pgvector."""

import asyncio
import json
from pathlib import Path
import os
import sys
import argparse

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.database import vector_store
from backend.config import settings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def main(force: bool = False, skip_if_exists: bool = False, sync: bool = False):
    """Load embeddings from JSON and insert into database."""

    print("🚀 Starting Render documentation ingestion")
    print(f"📍 Database: {settings.database_url[:50]}...")

    # Initialize database
    print("\n1️⃣ Initializing database connection...")
    await vector_store.initialize()

    # In sync mode, only sources not already present get inserted (additive, no wipe).
    existing_sources: set[str] = set()

    # Check if documents already exist
    existing_count = await vector_store.get_document_count()
    if existing_count > 0:
        print(f"\n⚠️  Database already contains {existing_count} documents")
        if force:
            print("🔄 Force mode: Deleting existing documents...")
            await vector_store.delete_all_documents()
            print("✅ Deleted")
        elif sync:
            async with vector_store.pool.acquire() as conn:
                rows = await conn.fetch("SELECT DISTINCT source FROM documents")
            existing_sources = {row["source"] for row in rows}
            print(
                f"🔁 Sync mode: {len(existing_sources)} sources already present; "
                "inserting only new sources"
            )
        elif skip_if_exists:
            print("⏭️  Skip-if-exists mode: database already populated, skipping ingestion")
            await vector_store.close()
            return
        else:
            response = input("Delete existing documents and re-ingest? (y/N): ")
            if response.lower() == 'y':
                print("Deleting existing documents...")
                await vector_store.delete_all_documents()
                print("✅ Deleted")
            else:
                print("❌ Aborted")
                await vector_store.close()
                return
    
    # Load embeddings from JSON
    embeddings_path = Path(__file__).parent.parent / "embeddings" / "render_docs.json"
    
    if not embeddings_path.exists():
        print(f"\n❌ Error: Embeddings file not found at {embeddings_path}")
        print("Please run generate_embeddings.py first")
        await vector_store.close()
        return
    
    print(f"\n2️⃣ Loading embeddings from {embeddings_path}")
    with open(embeddings_path, 'r') as f:
        docs = json.load(f)
    
    print(f"📄 Loaded {len(docs)} documents")

    # In sync mode, skip docs whose source is already in the database (additive load).
    if sync and existing_sources:
        before = len(docs)
        docs = [doc for doc in docs if doc['source'] not in existing_sources]
        print(f"🔁 Sync mode: {before - len(docs)} docs skipped (existing source), "
              f"{len(docs)} new docs to insert")
        if not docs:
            print("✅ Nothing new to ingest — database already up to date")
            await vector_store.close()
            return

    # Insert documents
    print("\n3️⃣ Inserting documents into database...")

    for i, doc in enumerate(docs, 1):
        title = doc['title']
        section = doc.get('section')
        source = doc['source']
        content = doc['content']
        embedding = doc['embedding']

        await vector_store.insert_document(
            content=content,
            source=source,
            title=title,
            embedding=embedding,
            section=section,
            metadata={
                'section': section,
                'word_count': len(content.split())
            }
        )
        
        print(f"  ✅ {i}/{len(docs)}: {title}")
    
    # Verify
    final_count = await vector_store.get_document_count()
    print(f"\n4️⃣ Verification")
    print(f"✅ Successfully ingested {final_count} documents")
    
    # Test similarity search
    print("\n5️⃣ Testing similarity search...")
    test_query = "How do I deploy a web service?"
    
    # Generate test embedding
    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    response = await openai_client.embeddings.create(
        model=settings.embedding_model,
        input=test_query,
        dimensions=settings.embedding_dimensions
    )
    test_embedding = response.data[0].embedding
    
    results = await vector_store.similarity_search(
        query_embedding=test_embedding,
        k=3
    )
    
    print(f"\nTest query: '{test_query}'")
    print(f"Found {len(results)} results:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result.metadata.get('title', 'Unknown')} (similarity: {result.similarity_score:.3f})")
    
    # Close connection
    await vector_store.close()
    
    print("\n✅ Ingestion complete!")
    print("\n🎉 Your Ask Render Anything Assistant is ready to use!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Render documentation into PostgreSQL")
    parser.add_argument('--force', '-f', action='store_true',
                       help='Force re-ingestion without confirmation')
    parser.add_argument('--skip-if-exists', action='store_true',
                       help='Skip ingestion silently if documents already exist (safe for deploy hooks)')
    parser.add_argument('--sync', action='store_true',
                       help='Additively insert only docs whose source is not already in the DB '
                            '(no wipe; safe for deploy hooks)')
    args = parser.parse_args()

    asyncio.run(main(force=args.force, skip_if_exists=args.skip_if_exists, sync=args.sync))

