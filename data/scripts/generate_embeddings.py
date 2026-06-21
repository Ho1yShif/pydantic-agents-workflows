"""Generate embeddings for Render documentation."""

import asyncio
import json
from pathlib import Path
from typing import List, Dict
import httpx
from openai import AsyncOpenAI
import os
import re
from dotenv import load_dotenv

from chunking import chunk_document
from crawl_tutorials import fetch_tutorial_docs

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def fetch_render_docs() -> List[Dict]:
    """
    Fetch actual Render documentation from llms-full.txt.
    
    This fetches the full documentation provided by Render for AI consumption.
    Excludes blog posts and articles, focusing only on technical documentation.
    """
    
    print("📡 Fetching documentation from https://render.com/docs/llms-full.txt...")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get("https://render.com/docs/llms-full.txt")
        response.raise_for_status()
        content = response.text
    
    print(f"✅ Fetched {len(content):,} characters of documentation")
    
    # Parse the documentation into chunks
    # The llms-full.txt format has sections separated by headers
    docs = []
    excluded_count = 0
    
    # Split by major sections (pages)
    # Look for lines starting with "# " (markdown h1 headers)
    pages = re.split(r'\n(?=# [^#])', content)
    
    print(f"📄 Found {len(pages)} major sections")
    
    for page in pages:
        if not page.strip():
            continue
            
        # Extract title (first h1)
        title_match = re.match(r'^# (.+?)$', page, re.MULTILINE)
        if not title_match:
            continue
            
        title = title_match.group(1).strip()
        
        # Extract source URL if present (format: "Source: https://...")
        source_match = re.search(r'^Source:\s+(https?://[^\s]+)', page, re.MULTILINE)
        source_url = source_match.group(1).strip() if source_match else "https://render.com/docs"
        
        # Split page into subsections by h2 headers
        subsections = re.split(r'\n(?=## [^#])', page)
        
        for i, subsection in enumerate(subsections):
            if not subsection.strip():
                continue
            
            # Extract section name if this is a subsection
            section_match = re.match(r'^## (.+?)$', subsection, re.MULTILINE)
            section_name = section_match.group(1).strip() if section_match else None
            
            # Clean up the content
            clean_content = subsection.strip()

            # Skip very small chunks
            if len(clean_content) < 100:
                continue

            # Exclude blog posts and articles (focus on technical docs only)
            if any(keyword in title.lower() for keyword in ['blog', 'article', 'changelog']):
                excluded_count += 1
                continue

            # Limit chunk size to ~2000 characters for better embedding quality
            docs.extend(chunk_document(
                title=title,
                section=section_name,
                source=source_url,
                content=clean_content,
            ))
    
    print(f"✅ Parsed into {len(docs)} documentation chunks")
    if excluded_count > 0:
        print(f"ℹ️  Excluded {excluded_count} blog/article sections (keeping only technical docs)")
    return docs


async def fetch_render_docs_sample() -> List[Dict]:
    """
    Sample Render documentation chunks (backup/demo mode).
    """
    
    sample_docs = [
        {
            "title": "Deploying a Web Service",
            "section": "Getting Started",
            "source": "https://docs.render.com/web-services",
            "content": """
To deploy a web service on Render:
1. Connect your GitHub or GitLab repository
2. Select the repository and branch to deploy
3. Render will automatically detect your runtime (Node, Python, Go, Rust, Ruby, Elixir, etc.)
4. Configure your build command (e.g., npm install, pip install -r requirements.txt)
5. Configure your start command (e.g., npm start, uvicorn main:app --host 0.0.0.0)
6. Choose your instance type (free, starter, standard, pro, pro plus, pro max, pro ultra)
7. Set environment variables
8. Click "Create Web Service"

Render will build and deploy your service automatically. You'll get a URL like https://your-service.onrender.com.
            """.strip()
        },
        {
            "title": "PostgreSQL Databases",
            "section": "Databases",
            "source": "https://docs.render.com/databases",
            "content": """
Render provides fully managed PostgreSQL databases with:
- Automated daily backups
- Point-in-time recovery
- Automatic minor version upgrades
- pgvector extension support for vector embeddings
- Connection pooling
- SSL encryption

Database plans range from free (256MB) to accelerated-1024gb.
You can create a database from the dashboard or using render.yaml.

Connection strings are automatically injected as environment variables to services in the same account.
            """.strip()
        },
        {
            "title": "Static Sites",
            "section": "Hosting",
            "source": "https://docs.render.com/static-sites",
            "content": """
Deploy static sites built with React, Vue, Angular, or plain HTML/CSS/JS.

Features:
- Automatic builds on git push
- Global CDN delivery
- Free SSL certificates
- Custom domains
- Branch deploys
- Pull request previews

Configuration:
- Build Command: The command to build your site (e.g., npm run build, yarn build)
- Publish Directory: The directory with built assets (e.g., build, dist, public)

Static sites are served over Render's global CDN for fast load times worldwide.
            """.strip()
        },
        {
            "title": "Environment Variables",
            "section": "Configuration",
            "source": "https://docs.render.com/configure-environment-variables",
            "content": """
Render supports environment variables for configuration:

1. Dashboard: Set in the service's Environment tab
2. render.yaml: Define in your Blueprint
3. Environment Groups: Share variables across multiple services

Environment variables are encrypted at rest and in transit.
They're available during builds and at runtime.

You can reference other services' connection strings:
- fromService for web services
- fromDatabase for PostgreSQL databases

Example:
envVars:
  - key: DATABASE_URL
    fromDatabase:
      name: my-postgres
      property: connectionString
            """.strip()
        },
        {
            "title": "Infrastructure as Code (render.yaml)",
            "section": "Configuration",
            "source": "https://docs.render.com/infrastructure-as-code",
            "content": """
render.yaml defines your entire infrastructure as code.

Benefits:
- Version control your infrastructure
- Reproduce environments easily
- Deploy multiple services together
- Share configurations

Structure:
services:
  - type: web
    name: my-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0
    plan: starter
    
databases:
  - name: my-db
    plan: free
    databaseName: mydb
    user: myuser

Render reads this file and creates/updates all resources automatically.
            """.strip()
        },
        {
            "title": "Autoscaling",
            "section": "Scaling",
            "source": "https://docs.render.com/scaling",
            "content": """
Render supports horizontal autoscaling for web services.

Configuration:
scaling:
  minInstances: 1
  maxInstances: 10
  targetCPUPercent: 70
  targetMemoryPercent: 80

Render automatically scales your service up when CPU or memory exceed targets,
and scales down during low usage.

Manual scaling is also available - you can set a specific number of instances.

Note: Autoscaling is available on Standard plans and above.
            """.strip()
        },
        {
            "title": "Node.js Support",
            "section": "Runtimes",
            "source": "https://docs.render.com/node-version",
            "content": """
Render supports Node.js versions 14, 16, 18, 20, and 22.

Specify version in package.json:
{
  "engines": {
    "node": "20.x"
  }
}

Render automatically:
- Detects Node.js projects
- Installs dependencies (npm install or yarn install)
- Builds your app (npm run build if present)
- Starts your app (npm start or specified start command)

Best practices:
- Use .nvmrc or engines field for version pinning
- Include package-lock.json or yarn.lock
- Set NODE_ENV=production for production builds
            """.strip()
        },
        {
            "title": "Python Support",
            "section": "Runtimes",
            "source": "https://docs.render.com/python-version",
            "content": """
Render supports Python 3.8, 3.9, 3.10, 3.11, and 3.12.

Specify version in runtime.txt:
python-3.11.5

Or in .python-version:
3.11.5

Render automatically:
- Detects requirements.txt or Pipfile
- Creates a virtual environment
- Installs dependencies

For FastAPI apps:
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT

For Django apps:
Build Command: pip install -r requirements.txt && python manage.py collectstatic --no-input
Start Command: gunicorn myproject.wsgi:application
            """.strip()
        },
        {
            "title": "Custom Domains",
            "section": "Networking",
            "source": "https://docs.render.com/custom-domains",
            "content": """
Add custom domains to your Render services:

1. Go to your service's Settings
2. Click "Add Custom Domain"
3. Enter your domain (e.g., api.example.com)
4. Add a CNAME record pointing to your Render service
5. Render automatically provisions SSL certificate

SSL certificates are:
- Automatically provisioned via Let's Encrypt
- Auto-renewed before expiration
- Included free with all plans

You can add multiple domains to a single service.
Render also supports apex domains (example.com) using ALIAS or ANAME records.
            """.strip()
        },
        {
            "title": "Health Checks",
            "section": "Monitoring",
            "source": "https://docs.render.com/health-checks",
            "content": """
Render performs health checks to ensure your service is running:

Default behavior:
- Render checks your service's root path (/)
- Expects HTTP 200-299 response
- Checks every 30 seconds

Custom health checks:
In render.yaml:
services:
  - type: web
    name: my-service
    healthCheckPath: /health

Best practices:
- Create a dedicated /health endpoint
- Check database connectivity
- Check external dependencies
- Return 200 OK when healthy
- Return 503 Service Unavailable when unhealthy

Render uses health checks for:
- Zero-downtime deploys
- Automatic restarts
- Load balancing
            """.strip()
        },
        {
            "title": "Background Workers",
            "section": "Service Types",
            "source": "https://docs.render.com/background-workers",
            "content": """
Background workers are services that don't accept HTTP requests.

Use cases:
- Process job queues (Celery, Bull, Sidekiq)
- Run scheduled tasks
- Handle async processing
- Send emails
- Generate reports

Configuration:
services:
  - type: worker
    name: my-worker
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: celery -A myapp worker

Workers can:
- Scale independently from web services
- Access same databases
- Share environment variables
- Use environment groups

Unlike web services, workers don't get a public URL.
            """.strip()
        },
        {
            "title": "Cron Jobs",
            "section": "Service Types",
            "source": "https://docs.render.com/cronjobs",
            "content": """
Run scheduled tasks with cron jobs.

Configuration:
services:
  - type: cron
    name: daily-backup
    env: python
    schedule: "0 2 * * *"
    buildCommand: pip install -r requirements.txt
    startCommand: python backup.py

Schedule syntax uses standard cron format:
- "0 2 * * *" = Daily at 2 AM
- "0 */6 * * *" = Every 6 hours
- "0 0 * * 0" = Weekly on Sunday
- "*/15 * * * *" = Every 15 minutes

Cron jobs:
- Run on a schedule
- Have access to environment variables
- Can connect to databases
- Are billed only when running

Perfect for backups, cleanup, report generation, etc.
            """.strip()
        },
        {
            "title": "Docker Support",
            "section": "Advanced",
            "source": "https://docs.render.com/docker",
            "content": """
Deploy containerized applications with Docker.

Render automatically detects Dockerfile and builds your image.

Example Dockerfile:
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]

In render.yaml:
services:
  - type: web
    name: my-docker-app
    env: docker
    dockerfilePath: ./Dockerfile
    dockerContext: .

Render:
- Builds your image on every deploy
- Caches layers for faster builds
- Supports multi-stage builds
- Can pull from private registries
            """.strip()
        },
        {
            "title": "Private Networking",
            "section": "Networking",
            "source": "https://docs.render.com/private-services",
            "content": """
Create private services that aren't accessible from the internet.

Configuration:
services:
  - type: pserv
    name: internal-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0

Private services:
- Only accessible from other services in your account
- No public URL
- Still get SSL/TLS encryption
- Can connect to databases
- Lower cost than public web services

Access from other services using:
envVars:
  - key: INTERNAL_API_URL
    fromService:
      name: internal-api
      type: pserv
      property: hostport
            """.strip()
        },
        {
            "title": "Redis",
            "section": "Databases",
            "source": "https://docs.render.com/redis",
            "content": """
Managed Redis instances for caching and real-time features.

Plans:
- Free: 25 MB
- Starter: 256 MB
- Standard: 1 GB
- Pro: Up to 16 GB

Features:
- Automatic failover
- Daily backups
- SSL encryption
- Connection pooling

Configuration in render.yaml:
services:
  - type: redis
    name: my-cache
    plan: starter
    ipAllowList: []

Access from your app:
envVars:
  - key: REDIS_URL
    fromService:
      name: my-cache
      type: redis
      property: connectionString

Perfect for session storage, caching, pub/sub, and queues.
            """.strip()
        },
        {
            "title": "Preview Environments",
            "section": "Development",
            "source": "https://docs.render.com/preview-environments",
            "content": """
Automatically deploy pull requests to isolated preview environments.

Benefits:
- Test changes before merging
- Share work with team
- Get feedback early
- Catch bugs before production

Configuration:
services:
  - type: web
    name: my-app
    previewsEnabled: true
    previewsExpireAfterDays: 7

When you open a PR:
1. Render automatically creates a preview environment
2. Deploys your PR branch
3. Provides a unique URL
4. Updates on every push to the PR

Preview environments are automatically deleted after the PR is merged or closed.

Great for frontend apps, APIs, and full-stack applications.
            """.strip()
        },
        {
            "title": "Build Optimization",
            "section": "Performance",
            "source": "https://docs.render.com/build-performance",
            "content": """
Speed up your builds with these tips:

1. Use dependency caching:
   - Render caches node_modules, pip cache, etc.
   - Only reinstalls changed dependencies

2. Optimize Docker builds:
   - Copy package files first
   - Run npm install before copying code
   - Use multi-stage builds

3. Reduce build artifacts:
   - Remove dev dependencies in production
   - Use .dockerignore or .gitignore
   - Avoid copying large files

4. Pre-build when possible:
   - Build locally and commit dist/
   - Use CI/CD for heavy builds
   - Skip build command if no build needed

Example optimized Dockerfile:
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
CMD ["node", "server.js"]
            """.strip()
        },
        {
            "title": "Monitoring and Alerts",
            "section": "Observability",
            "source": "https://docs.render.com/monitoring",
            "content": """
Monitor your services with built-in metrics:

Available metrics:
- CPU usage
- Memory usage
- Request rate
- Response time
- Error rate
- Bandwidth

Alerts:
- Configure email notifications
- Set thresholds for metrics
- Get notified of deploys and failures

Integration with external tools:
- Export logs to external services
- Use Logfire, Datadog, New Relic, etc.
- Custom metrics via StatsD

View metrics in the Render dashboard:
- Real-time graphs
- Historical data (30 days)
- Per-instance breakdown

Best practices:
- Set up health checks
- Monitor error rates
- Track response times
- Set up alerts for critical services
            """.strip()
        },
        {
            "title": "Zero-Downtime Deploys",
            "section": "Deployment",
            "source": "https://docs.render.com/deploys",
            "content": """
Render performs zero-downtime deploys automatically:

How it works:
1. Build new version of your service
2. Start new instances
3. Wait for health checks to pass
4. Route traffic to new instances
5. Drain connections from old instances
6. Stop old instances

This happens automatically for web services on paid plans.

Manual deploys:
- Click "Manual Deploy" in dashboard
- Use Render API
- Trigger via webhook

Deploy hooks:
- Pre-deploy commands
- Post-deploy commands
- Database migrations

Best practices:
- Use health checks
- Test deploys in preview environments
- Monitor deploy metrics
- Keep deploys small and frequent
            """.strip()
        },
        {
            "title": "Logging",
            "section": "Observability",
            "source": "https://docs.render.com/logging",
            "content": """
Access logs for debugging and monitoring:

Types of logs:
- Application logs (stdout/stderr)
- Build logs
- System logs
- Deploy logs

View logs:
- Dashboard: Live tail in real-time
- CLI: render logs <service-name>
- API: Programmatic access

Log retention:
- Free: 7 days
- Paid: 30 days

Export logs to external services:
- Logfire
- Datadog
- Papertrail
- Logtail
- Custom HTTP endpoint

Best practices:
- Log to stdout/stderr
- Use structured logging (JSON)
- Include timestamps
- Don't log sensitive data
- Use log levels (DEBUG, INFO, WARN, ERROR)
            """.strip()
        },
        {
            "title": "Secrets Management",
            "section": "Security",
            "source": "https://docs.render.com/security",
            "content": """
Securely manage secrets and credentials:

Environment variables:
- Encrypted at rest
- Encrypted in transit
- Not visible in logs
- Not exposed to preview environments (unless configured)

Best practices:
1. Never commit secrets to git
2. Use environment variables for API keys
3. Rotate secrets regularly
4. Use separate keys for different environments
5. Limit access to production secrets

Environment groups:
- Share secrets across services
- Update in one place
- Control access

For highly sensitive data:
- Use external secret managers (AWS Secrets Manager, HashiCorp Vault)
- Fetch secrets at runtime
- Use short-lived tokens

Render complies with:
- SOC 2 Type II
- GDPR
- HIPAA (on Team plans)
            """.strip()
        }
    ]
    
    return sample_docs


async def generate_embedding(text: str) -> List[float]:
    """Generate embedding for text with exponential backoff retry on rate limits."""
    import openai

    for attempt in range(5):
        try:
            response = await openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
                dimensions=1536
            )
            return response.data[0].embedding
        except openai.RateLimitError as e:
            if attempt == 4:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s, 8s
            print(f"\n  ⏳ Rate limited, retrying in {wait}s...")
            await asyncio.sleep(wait)


def validate_api_keys():
    """Validate required API keys are set."""
    print("🔑 Checking API keys...")
    
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key or openai_key == "sk-...":
        print("\n❌ ERROR: OPENAI_API_KEY not set in .env file")
        print("   Get your key at: https://platform.openai.com/api-keys")
        return False
    
    print(f"✅ OpenAI API key found (starts with: {openai_key[:10]}...)")
    return True


async def test_database_connection():
    """Test database connection before doing expensive operations."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from backend.config import settings
    import asyncpg
    
    print("🔍 Testing database connection...")
    print(f"   Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'unknown'}")
    
    try:
        conn = await asyncpg.connect(settings.database_url)
        await conn.execute("SELECT 1")
        
        # Check if vector extension is available
        result = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
        if not result:
            print("\n⚠️  WARNING: pgvector extension not found")
            print("   Run: docker-compose exec postgres psql -U render_qa_user -d render_qa_db -c 'CREATE EXTENSION vector;'")
        
        await conn.close()
        print("✅ Database connection successful!\n")
        return True
    except asyncpg.InvalidPasswordError:
        print("\n❌ ERROR: Database authentication failed")
        print("   Check your DATABASE_URL in .env file")
        print("   Expected format: postgresql://render_qa_user:local_dev_password@localhost:5432/render_qa_db")
        return False
    except asyncpg.PostgresConnectionError as e:
        print(f"\n❌ ERROR: Cannot connect to database")
        print(f"   {e}")
        print("   Make sure PostgreSQL is running: docker-compose ps")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: Database connection failed")
        print(f"   {e}")
        return False


async def main():
    """Generate embeddings for all documentation."""
    
    print("🚀 Starting Render documentation embedding generation")
    print("=" * 60)
    print()
    
    # Validate prerequisites BEFORE doing expensive operations
    if not validate_api_keys():
        print("\n⚠️  Fix the API key configuration and try again")
        return
    
    print()
    
    # Test database connection BEFORE fetching docs and generating embeddings
    if not await test_database_connection():
        print("⚠️  Fix the database connection and try again")
        print("   Hint: Run 'docker-compose up -d' to start the database")
        return
    
    try:
        docs = await fetch_render_docs()
    except Exception as e:
        print(f"\n⚠️  Error fetching documentation: {e}")
        print("Falling back to sample documentation...")
        docs = await fetch_render_docs_sample()

    # Crawl the Tutorials section (not included in llms-full.txt) and append it.
    print("\n📚 Crawling render.com/tutorials...")
    try:
        tutorial_docs = await fetch_tutorial_docs()
        docs.extend(tutorial_docs)
        print(f"➕ Added {len(tutorial_docs)} tutorial chunks")
    except Exception as e:
        print(f"\n⚠️  Error crawling tutorials: {e}")
        print("Continuing without tutorial content...")

    print(f"\n📊 Processing {len(docs)} documentation chunks")
    
    print("\n🔄 Generating embeddings with OpenAI...")
    print("(This may take a few minutes depending on the amount of content)\n")
    
    embedded_docs = []
    for i, doc in enumerate(docs, 1):
        title = doc['title'][:60] + "..." if len(doc['title']) > 60 else doc['title']
        print(f"  [{i:3d}/{len(docs)}] {title}")
        
        # Generate embedding for the content
        embedding = await generate_embedding(doc['content'])
        
        embedded_doc = {
            **doc,
            "embedding": embedding
        }
        
        embedded_docs.append(embedded_doc)
        
        # Delay to stay under 100 RPM limit (need >0.6s per request)
        await asyncio.sleep(0.65)
        
        # Show progress every 50 chunks
        if i % 50 == 0:
            print(f"\n  ✅ Completed {i}/{len(docs)} chunks ({i*100//len(docs)}%)\n")
    
    # Save to JSON file
    output_path = Path(__file__).parent.parent / "embeddings" / "render_docs.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(embedded_docs, f, indent=2)
    
    print("\n" + "=" * 60)
    print("✅ SUCCESS!")
    print(f"📊 Generated embeddings for {len(embedded_docs)} documentation chunks")
    print(f"📁 Saved to: {output_path}")
    print(f"💾 File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
    print("\n🎯 Next step: Run 'make ingest' or 'python data/scripts/ingest_docs.py'")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

