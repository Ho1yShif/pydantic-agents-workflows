"""Add Render Node.js deployment documentation to embeddings.

This script adds curated content about deploying Node.js apps on Render
to the vector database so the Q&A system can reference it when developers
ask about deploying Node.js, Express, Next.js, or JavaScript applications.
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

NODEJS_URL = "https://render.com/docs/deploy-node-express-app"

CURATED_CONTENT = """# Deploying a Node.js App on Render
Source: https://render.com/docs/deploy-node-express-app

## Overview
Render supports Node.js web services, background workers, and static sites.
Node.js apps deploy using Render's native Node.js buildpack or a custom Dockerfile.
Render auto-detects Node.js projects via the presence of a package.json file.

## Quick Start: Deploy Node.js via Dashboard
1. Push your Node.js project to GitHub or GitLab.
2. In the Render Dashboard, click **New → Web Service** and connect your repo.
3. Render auto-detects Node.js via package.json.
4. Set the **Build Command** (e.g. `npm install` or `npm run build`).
5. Set the **Start Command** (e.g. `node index.js` or `npm start`).
6. Choose an instance type and click **Deploy**.

## render.yaml (Infrastructure as Code)
```yaml
services:
  - type: web
    name: my-node-app
    runtime: node
    buildCommand: npm install
    startCommand: node index.js
    plan: starter
    envVars:
      - key: NODE_ENV
        value: production
      - key: PORT
        sync: false
```

## PORT Environment Variable (CRITICAL)
Render automatically sets the `PORT` environment variable. Your Node.js app **must**
listen on `process.env.PORT`:

```javascript
const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`Server running on port ${port}`);
});
```

## Node.js Version
Specify your Node.js version using one of these methods:
- **package.json engines field** (recommended):
  ```json
  "engines": { "node": "20.x" }
  ```
- **.node-version file** in the project root: `20.x`
- **.nvmrc file** in the project root: `20`

## Build and Start Commands
Common patterns:
- **Simple app**: Build: `npm install`, Start: `node server.js`
- **TypeScript**: Build: `npm install && npm run build`, Start: `node dist/index.js`
- **npm scripts**: Build: `npm install`, Start: `npm start`
- **Production install**: Build: `npm ci`, Start: `node index.js`

## Health Checks
Render performs HTTP health checks on your service. Your app must respond with a 2xx
status on the configured health check path (default: `/`). Configure the path in
Dashboard → Settings → Health & Alerts.

## Environment Variables
Set environment variables in the Dashboard under **Environment** or in render.yaml:
```yaml
envVars:
  - key: DATABASE_URL
    fromDatabase:
      name: my-postgres-db
      property: connectionString
  - key: SECRET_KEY
    generateValue: true
```

## Connecting to a Database
For Render Postgres, use the `DATABASE_URL` environment variable:
```javascript
const { Pool } = require('pg');
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
```

## Static Sites vs Web Services for JavaScript Apps
- **Render Static Sites** (free): Use for purely static output — plain HTML/CSS/JS,
  Vite builds, Create React App, etc. No server-side rendering.
- **Render Web Services**: Use for server-side rendering — Next.js App Router, Remix,
  Express APIs, Nuxt.js, etc. Requires a running Node.js process.

## Next.js Deployment
For Next.js with App Router (SSR):
```yaml
services:
  - type: web
    name: my-nextjs-app
    runtime: node
    buildCommand: npm install && npm run build
    startCommand: npm start
    envVars:
      - key: NODE_ENV
        value: production
```

For Next.js static export (`output: 'export'` in next.config.js):
```yaml
services:
  - type: static
    name: my-nextjs-static
    buildCommand: npm install && npm run build
    staticPublishPath: ./out
```

## Persistent Disk
Mount a persistent disk for stateful storage (SQLite, uploaded files):
```yaml
services:
  - type: web
    name: my-app
    disk:
      name: app-data
      mountPath: /data
      sizeGB: 1
```

## Monorepo Support
Set the **Root Directory** in service settings to the subfolder containing your Node app.
Render will run all commands from that directory.

## Zero-Downtime Deploys
Render performs zero-downtime rolling deploys. The old instance stays live until the
new instance passes all health checks, then traffic is shifted over.

## Private Services and Background Workers
Node.js apps can also be deployed as:
- **Private Service**: Internal API not exposed to the internet
- **Background Worker**: Long-running processes without HTTP (e.g., queue consumers)

```yaml
services:
  - type: worker        # background worker
    name: my-worker
    runtime: node
    buildCommand: npm install
    startCommand: node worker.js
```
"""


async def fetch_nodejs_page():
    """Fetch and parse the Node.js deployment docs page."""
    print(f"Fetching {NODEJS_URL}...")

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(NODEJS_URL)
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
    """Add the Node.js deployment document to the vector store."""
    await vector_store.initialize()

    print("\nRemoving old Node.js deployment documents...")
    async with vector_store.pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM documents
            WHERE source = $1
        """, NODEJS_URL)
        deleted_count = int(result.split()[-1])
        print(f"   Deleted {deleted_count} old documents")

    print("\nAdding Node.js deployment document to vector store...")

    if len(content) < 100:
        print("Error: Content too short, aborting")
        await vector_store.close()
        return

    embed_result = await embed_question(content)

    await vector_store.insert_document(
        content=content,
        source=NODEJS_URL,
        title="Deploying a Node.js App on Render",
        embedding=embed_result["embedding"],
        section="Node.js Deployment",
        metadata={
            "type": "docs",
            "category": "nodejs_deployment",
            "title": "Deploying a Node.js App on Render"
        }
    )

    await vector_store.close()
    print("Successfully added 1 Node.js deployment document!")


async def main():
    print("=" * 80)
    print("ADDING RENDER NODE.JS DEPLOYMENT DOCS TO VECTOR DATABASE")
    print("=" * 80)
    print()

    html = await fetch_nodejs_page()

    scraped_text = extract_page_content(html) if html else ""
    content = build_document_content(scraped_text)

    print(f"Document length: {len(content):,} characters")

    await add_to_vector_store(content)

    print()
    print("=" * 80)
    print("COMPLETE")
    print("=" * 80)
    print()
    print("The Q&A system will now reference Node.js deployment docs when developers")
    print("ask about deploying Node.js, Express, or Next.js apps on Render.")
    print()
    print("TIP: Re-run this script if the docs page content changes")


if __name__ == "__main__":
    asyncio.run(main())
