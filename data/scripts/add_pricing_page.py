"""Add Render pricing page to documentation embeddings.

This script dynamically fetches the latest pricing information from
https://render.com/pricing and adds it to the vector database.
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


async def fetch_pricing_page():
    """Fetch and parse the pricing page from render.com."""
    print("📡 Fetching https://render.com/pricing...")
    
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get("https://render.com/pricing")
        response.raise_for_status()
    
    print(f"✅ Fetched {len(response.text):,} characters")
    return response.text


def extract_table_data(table):
    """Extract data from an HTML table element."""
    rows = []
    
    # Extract headers
    headers = []
    header_row = table.find('thead')
    if header_row:
        for th in header_row.find_all(['th', 'td']):
            headers.append(th.get_text(strip=True))
    
    # Extract body rows
    body = table.find('tbody')
    if body:
        for tr in body.find_all('tr'):
            row = []
            for td in tr.find_all(['td', 'th']):
                # Clean up cell text
                text = td.get_text(strip=True)
                # Remove excessive whitespace
                text = ' '.join(text.split())
                row.append(text)
            if row:  # Only add non-empty rows
                rows.append(row)
    
    return headers, rows


def format_table_as_text(headers, rows, title):
    """Format table data as readable text with context for better semantic matching."""
    if not rows:
        return None
    
    # Create header line with descriptive context for semantic search
    lines = [f"# {title}", "Source: https://render.com/pricing", ""]
    
    # Add context based on service type for better retrieval
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
    
    # Add data rows
    for row in rows:
        lines.append(" | ".join(row))
    
    return "\n".join(lines)


async def parse_pricing_tables(html):
    """Parse pricing tables from the HTML."""
    soup = BeautifulSoup(html, 'lxml')
    
    pricing_docs = []
    
    # Find all tables
    tables = soup.find_all('table')
    print(f"📊 Found {len(tables)} tables on pricing page")
    
    for i, table in enumerate(tables, 1):
        # Try to determine service type from table content
        table_text = table.get_text().lower()
        
        # Identify service type by looking for distinctive terms in the table
        if 'postgres' in table_text or 'accelerated' in table_text or 'basic-' in table_text:
            title = "Render Postgres Pricing"
        elif 'key value' in table_text or ('starter' in table_text and 'connection limit' in table_text):
            title = "Render Key Value Pricing"
        elif 'cron' in table_text or '/minute' in table_text:
            title = "Render Cron Jobs Pricing"
        elif 'web service' in table_text or 'pro max' in table_text or 'pro ultra' in table_text:
            title = "Render Web Services Pricing"
        else:
            # Fallback: Look for preceding headings
            prev_heading = table.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            if prev_heading:
                title = prev_heading.get_text(strip=True)
                title = ' '.join(title.split())
            else:
                title = f"Render Pricing Table {i}"
        
        print(f"  {i}. {title}")
        
        # Extract table data
        headers, rows = extract_table_data(table)
        
        if rows:
            # Format as text
            table_text_formatted = format_table_as_text(headers, rows, title)
            
            if table_text_formatted:
                pricing_docs.append({
                    'title': title,
                    'content': table_text_formatted
                })
    
    print(f"✅ Extracted {len(pricing_docs)} pricing documents")
    return pricing_docs


async def add_to_vector_store(docs):
    """Add pricing documents to vector store."""
    await vector_store.initialize()
    
    # First, remove old pricing documents to avoid duplicates
    print("\n🗑️  Removing old pricing documents...")
    async with vector_store.pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM documents
            WHERE source = 'https://render.com/pricing'
        """)
        deleted_count = int(result.split()[-1])
        print(f"   Deleted {deleted_count} old pricing documents")
    
    print(f"\n📦 Adding {len(docs)} pricing documents to vector store...")
    
    added_count = 0
    for i, doc in enumerate(docs, 1):
        print(f"  {i}/{len(docs)}: {doc['title']}")
        
        # Skip if content is too short (likely not useful)
        if len(doc['content']) < 100:
            print(f"    ⚠️  Skipping (too short: {len(doc['content'])} chars)")
            continue
        
        try:
            # Generate embedding
            embed_result = await embed_question(doc['content'])
            
            # Insert into database
            await vector_store.insert_document(
                content=doc['content'],
                source="https://render.com/pricing",
                title=doc['title'],
                embedding=embed_result["embedding"],
                section=doc['title'],
                metadata={
                    "type": "pricing",
                    "title": doc['title']
                }
            )
            added_count += 1
        except Exception as e:
            print(f"    ❌ Error: {e}")
    
    await vector_store.close()
    print(f"\n✅ Successfully added {added_count}/{len(docs)} pricing documents!")


async def main():
    print("=" * 80)
    print("🏷️  ADDING RENDER PRICING PAGE TO VECTOR DATABASE")
    print("=" * 80)
    print()
    
    # Fetch pricing page
    html = await fetch_pricing_page()
    
    # Parse tables
    docs = await parse_pricing_tables(html)
    
    if not docs:
        print("❌ No pricing tables found!")
        return
    
    # Add to vector store
    await add_to_vector_store(docs)
    
    print()
    print("=" * 80)
    print("✅ COMPLETE")
    print("=" * 80)
    print()
    print("Your RAG system now has access to live pricing data from render.com/pricing!")
    print()
    print("💡 TIP: Run this script periodically to keep pricing data up-to-date")


if __name__ == "__main__":
    asyncio.run(main())
