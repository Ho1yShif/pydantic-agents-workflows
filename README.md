# Pydantic Agents

> Render Developer Q&A Assistant showcasing observable AI with Pydantic Agents, Pydantic Embedder, Logfire, and Render

<a href="https://render.com/deploy?repo=https://github.com/render-examples/pydantic-agents">
  <img src="https://render.com/images/deploy-to-render-button.svg" alt="Deploy to Render" height="32">
</a>

Intelligent question-answering system that demonstrates real-world AI observability patterns. This example project shows how to build, instrument, and monitor a multi-stage LLM pipeline with full cost tracking, quality evaluation, and performance monitoring.

## Table of Contents

- [What This App Does](#what-this-app-does)
- [What This Demonstrates](#what-this-demonstrates)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Deploy to Render](#deploy-to-render)
- [Example Metrics](#example-metrics)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## What This App Does

This is an **AI-powered Q&A assistant for Render documentation**. Users can ask questions about Render's platform, and the app provides accurate, well-researched answers backed by the official documentation.

### User Experience

1. **Ask a question** - "How do I deploy a Node.js app on Render?" or "What database plans are available?"
2. **Watch the pipeline** - See real-time progress through 8 stages (embedding → retrieval → generation → verification)
3. **Get accurate answers** - Receive detailed responses with sources from Render docs
4. **Quality guaranteed** - Every answer is verified for accuracy and rated by dual AI evaluators

### Key Features

- **Hybrid search** - Combines semantic understanding with keyword matching for better retrieval
- **Multi-stage verification** - Extracts claims, verifies against docs, checks technical accuracy
- **Iterative refinement** - Automatically regenerates low-quality answers with feedback
- **Cost tracking** - See exactly how much each question costs to answer
- **Real-time streaming** - Progressive response updates via Server-Sent Events

### Example Questions

```
"How do I set up PostgreSQL on Render?"
"What's the difference between Web Services and Static Sites?"
"How much does a Starter plan cost?"
"Can I use custom domains with Render?"
"How do I configure environment variables?"
```

The app answers questions about deployment, databases, pricing, configuration, networking, and all other Render platform features based on ~10,000 documentation chunks.

---

## What This Demonstrates

### Logfire Features

- **LLM Traces** - Complete visibility into every AI call (OpenAI + Anthropic auto-instrumented)
- **HTTP Tracing** - FastAPI auto-instrumentation for request/response tracking
- **Database Monitoring** - AsyncPG auto-instrumentation for query performance
- **Cost Tracking** - Per-stage and per-execution cost attribution with custom metrics
- **Multi-Model Evals** - Dual-rater quality assessment (OpenAI + Anthropic)
- **Session Tracking** - End-to-end user journey with distributed tracing
- **Custom Metrics** - Business-specific metrics (cost, quality, iterations)
- **SQL Queries** - Custom analytics on AI performance

### Pydantic Stack

This project is built end-to-end on the [Pydantic](https://pydantic.dev/) ecosystem:

- **[Pydantic AI Agents](https://ai.pydantic.dev/agents/)** — every pipeline stage (generation, claims extraction, accuracy check, dual-rater evaluation) is a `pydantic_ai.Agent` with a typed `output_type`. Multi-provider orchestration (Claude + GPT) runs through `OpenAIProvider` / `AnthropicProvider` in a single pipeline. See [`backend/pipeline/`](./backend/pipeline/).
- **[Pydantic Embedder](https://ai.pydantic.dev/embeddings/)** — `pydantic_ai.Embedder` with `OpenAIEmbeddingModel` powers question embedding (`embed_query`) and batch claim embedding (`embed_documents`) for verification. Auto-instrumented by `logfire.instrument_pydantic_ai()`. See [`backend/pipeline/embeddings.py`](./backend/pipeline/embeddings.py) and [`backend/pipeline/verification.py`](./backend/pipeline/verification.py).
- **[Pydantic Models](https://docs.pydantic.dev/)** — Claims, accuracy scores, eval dimensions, and pipeline state are parsed directly into Pydantic models (e.g. `ClaimsOutput`, `EvaluationOutput`). `pydantic-settings` manages config in [`backend/config.py`](./backend/config.py).
- **[Pydantic GenAI Prices](https://github.com/pydantic/genai-prices)** — model pricing is loaded dynamically from the `pydantic/genai-prices` registry, then combined with per-agent token counts from `result.usage()` to produce per-stage cost attribution. See [`backend/prices.py`](./backend/prices.py).
- **[Logfire](https://logfire.pydantic.dev/)** — distributed traces, custom metrics, dual-model evals, and cost attribution. Auto-instruments FastAPI, AsyncPG, HTTPX, and Pydantic AI. See [`backend/observability.py`](./backend/observability.py).

### Render Capabilities

- **Zero-Config Deployment** - Push to deploy with render.yaml
- **PostgreSQL with pgvector + full-text** - Managed hybrid search database
- **Web Service + Static Site** - Full-stack deployment
- **Environment Management** - Secure secrets handling
- **Auto-Scaling** - Handle variable AI workloads

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript)                              │
│  Deployed as: Render Static Site                            │
│  - Question input UI                                        │
│  - Real-time progress via SSE                               │
│  - Answer display with metrics                              │
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTPS
┌─────────────────────────────────────────────────────────────┐
│  Backend API (FastAPI + Pydantic AI + Logfire)              │
│  Deployed as: Render Web Service (Python 3.13)              │
│                                                             │
│  8-Stage Pipeline:                                          │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [1] Question Embedding      (OpenAI)                   │ │
│  │ [2] RAG Document Retrieval  (pgvector + BM25)          │ │
│  │ [3] Answer Generation       (Claude Sonnet 4.6)        │ │
│  │ [4] Claims Extraction       (GPT-5.4-mini)             │ │
│  │ [5] Claims Verification     (RAG again)                │ │
│  │ [6] Technical Accuracy      (Claude Sonnet 4.6)        │ │
│  │ [7] Quality Rating          (OpenAI + Anthropic)       │ │
│  │ [8] Quality Gate            (Pass or Iterate)          │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
            ↓                                    ↓
┌──────────────────────┐           ┌───────────────────────────┐
│  PostgreSQL          │           │  Logfire                  │
│  (Render Managed)    │           │  (Pydantic)               │
│  - pgvector ext      │           │  - Distributed traces     │
│  - RAG embeddings    │           │  - Cost attribution       │
│  - Full-text search  │           │  - Quality metrics        │
└──────────────────────┘           │  - Custom dashboards      │
                                   └───────────────────────────┘
```

### Project Structure

```
render-qa-assistant/
├── backend/
│   ├── main.py                    # FastAPI application entry
│   ├── requirements.txt           # Legacy pip dependencies (reference only)
│   ├── api/
│   │   └── logs.py                # Logfire logs API endpoint
│   ├── pipeline/                  # 8-stage pipeline implementation
│   ├── models.py                  # Pydantic models
│   ├── database.py                # PostgreSQL + pgvector
│   ├── observability.py           # Logfire configuration
│   └── config.py                  # Settings management
├── frontend/
│   ├── src/                       # React + TypeScript UI
│   ├── package.json
│   └── vite.config.ts
├── data/
│   ├── embeddings/                # Pre-embedded documentation
│   └── scripts/                   # Data ingestion scripts
├── docs/
│   ├── PIPELINE.md                # Detailed pipeline guide
│   ├── OBSERVABILITY.md           # Logfire instrumentation guide
│   ├── CONFIGURATION.md           # Configuration reference
│   └── HYBRID_SEARCH.md           # Hybrid search deep-dive
├── pyproject.toml                 # Python dependencies (uv)
├── uv.lock                        # Locked dependency versions
├── .python-version                # Pins Python to 3.13
├── render.yaml                    # Infrastructure as code
├── .env.example                   # Environment variables template
└── README.md                      # This file
```

---

## Quick Start

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (manages Python 3.13 automatically)
- Node.js 18+
- PostgreSQL 16+ (with pgvector extension)
- OpenAI API key
- Anthropic API key
- **Logfire account** — sign in at [logfire.pydantic.dev](https://logfire.pydantic.dev), create a project (US region), then:
  1. **Settings → Write Tokens** → create a token → `LOGFIRE_TOKEN` in `.env`
  2. **Settings → Read Tokens** → create a token → `LOGFIRE_READ_TOKEN` in `.env`
  3. View traces in the **Live** panel under your project

### Local Development (with Make)

```bash
# 1. Install everything (uv installs Python 3.13 automatically)
make install

# 2. Set up .env file (copy from example and fill in your keys)
cp .env.example .env

# 3. Start database
make db-start

# 4. Load documentation (this step might take a while!)
make ingest

# 5. Run backend (in one terminal)
make run-backend

# 6. Run frontend (in another terminal)
make run-frontend
```

`make ingest` runs the full pipeline: bulk doc embeddings, plus the curated "special pages" that get explicit-injection into RAG context (pricing, AI agent, autoscaling, Node.js). To re-load just one of those after editing its script, use the per-target shortcuts:

```bash
make add-pricing      # render.com/pricing tables
make add-ai-agent     # render.com/tutorials/agents-on-render-workflows (AI agents → Render Workflows)
make add-autoscaling  # render.com/docs/scaling
make add-nodejs       # render.com/docs/deploy-node-express-app
```

When a developer asks "How do I deploy an AI agent on Render?", the only context injected is the [Render Workflows agents tutorial](https://render.com/tutorials/agents-on-render-workflows/what-youll-build) — bringing home the canonical answer: the best way to run AI agents on Render is Render Workflows.

### Manual Setup

```bash
# 1. Install Python dependencies (uv reads .python-version → 3.13)
uv sync --group dev

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start PostgreSQL with Docker
docker-compose up -d

# 4. Generate and load documentation
uv run python data/scripts/generate_embeddings.py
uv run python data/scripts/ingest_docs.py

# 5. Run backend (from project root)
uv run uvicorn backend.main:app --reload --port 8000

# 6. Run frontend (separate terminal)
cd frontend && npm install && npm run dev
```

**Access locally:**

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Logfire: https://logfire.pydantic.dev

---

## Deploy to Render

### 1. Set up a Logfire account.

Before clicking the deploy button, sign in at [logfire.pydantic.dev](https://logfire.pydantic.dev), create a project (US region), and generate two tokens:

- **Preferences → Write Tokens** → create token → save as `LOGFIRE_TOKEN`
- **Preferences → Read Tokens** → create token → save as `LOGFIRE_READ_TOKEN`

You'll paste both into the Render Dashboard in step 3.

### 2. One-click deploy

<a href="https://render.com/deploy?repo=https://github.com/render-examples/pydantic-agents">
  <img src="https://render.com/images/deploy-to-render-button.svg" alt="Deploy to Render" height="32">
</a>

Render reads [`render.yaml`](./render.yaml) and provisions:

- PostgreSQL database with pgvector (`pydantic-agents-db`)
- Backend API web service (`pydantic-agents-api`, FastAPI + Pydantic AI + Logfire)
- Frontend static site (`pydantic-agents-frontend`, Next.js)

### 3. Fill in environment variables

You'll be prompted only for these four secrets:

| Variable | Source |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `LOGFIRE_TOKEN` | Logfire write token from step 1 |
| `LOGFIRE_READ_TOKEN` | Logfire read token from step 1 |

**Auto-filled by Render (no action needed):** `DATABASE_URL` (injected from the database service), `QUALITY_THRESHOLD`, `ACCURACY_THRESHOLD`, `MAX_ITERATIONS`, `MAX_TOKENS`, `RAG_TOP_K`, `SIMILARITY_THRESHOLD`, `VERIFICATION_THRESHOLD`, `ENABLE_CACHING`, `LOG_LEVEL`.

### 4. Wire the frontend to the backend

After the backend deploys, copy its public URL (`https://pydantic-agents-api-XXXX.onrender.com`) and set it as the `NEXT_PUBLIC_API_URL` env var on the **frontend** service. Trigger a redeploy of the frontend so the new value takes effect.

### 5. Done

- Backend: `https://pydantic-agents-api-XXXX.onrender.com`
- Frontend: `https://pydantic-agents-frontend-XXXX.onrender.com`

Doc ingestion runs automatically as a `preDeployCommand` on every backend deploy. The bulk corpus is loaded once via `ingest_docs.py --skip-if-exists`; the curated special pages (`add_pricing_page.py`, `add_workflows_tutorial_page.py`, `add_autoscaling_page.py`, `add_nodejs_page.py`) re-run on every deploy so canonical answers stay in sync with the latest source pages.

---

## Example Metrics

### Cost Breakdown (per question)

```
┌────────────────────────────────┬──────────┬──────────┐
│ Stage                          │ Cost     │ % Total  │
├────────────────────────────────┼──────────┼──────────┤
│ Question Embedding             │ $0.0002  │    2%    │
│ RAG Retrieval                  │ $0.0001  │    1%    │
│ Answer Generation (Claude)     │ $0.0450  │   56%    │
│ Claims Extraction (GPT)        │ $0.0080  │   10%    │
│ Claims Verification (RAG)      │ $0.0015  │    2%    │
│ Accuracy Check (Claude)        │ $0.0180  │   22%    │
│ Quality Rating (Dual)          │ $0.0070  │    9%    │
├────────────────────────────────┼──────────┼──────────┤
│ TOTAL (first iteration)        │ $0.0798  │  100%    │
└────────────────────────────────┴──────────┴──────────┘
```

### Performance Metrics

- **Average Response Time:** 4.2 seconds (first iteration)
- **P95 Response Time:** 8.7 seconds
- **Iteration Rate:** 12% of questions require refinement
- **Success Rate:** 95% accuracy (validated by dual evaluators)

### Quality Scores

- **Average Quality Score:** 89/100
- **OpenAI Average:** 87/100
- **Anthropic Average:** 91/100
- **Inter-rater Agreement:** 77% (within 10 points)

---

## Documentation

### Core Guides

- **[docs/PIPELINE.md](./docs/PIPELINE.md)** - Detailed breakdown of the 8-stage pipeline
- **[docs/OBSERVABILITY.md](./docs/OBSERVABILITY.md)** - Comprehensive Logfire instrumentation guide
- **[docs/CONFIGURATION.md](./docs/CONFIGURATION.md)** - All configuration options and tuning
- **[docs/HYBRID_SEARCH.md](./docs/HYBRID_SEARCH.md)** - Technical deep-dive on hybrid search

### External Resources

- **Logfire Documentation:** https://docs.pydantic.dev/logfire/
- **Pydantic AI Documentation:** https://ai.pydantic.dev/
- **Render Documentation:** https://docs.render.com/

---

## Contributing

This is a demo project, but improvements are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

## License

MIT License - see LICENSE file for details

---

## Acknowledgments

Built to showcase:

- **Logfire** by Pydantic - AI observability platform
- **Render** - Modern cloud platform
- **Pydantic AI** - Type-safe AI agent framework
- **OpenAI & Anthropic** - LLM providers

---

**Ready to build observable AI?** Fork this repo and deploy to Render to get started!
