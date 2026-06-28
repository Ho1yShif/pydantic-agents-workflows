# Pydantic Agents

> Render Developer Q&A Assistant showcasing observable AI with Pydantic Agents, Pydantic Embedder, and Logfire

<a href="https://render.com/deploy?repo=https://github.com/render-examples/pydantic-agents-workflows">
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
2. **Watch the pipeline** - Track progress as the run moves through 7 stages (embedding → retrieval → generation → verification)
3. **Get accurate answers** - Receive detailed responses with sources from Render docs
4. **Quality guaranteed** - Every answer is verified for accuracy and rated by dual AI evaluators

### Key Features

- **Hybrid search** - Combines semantic understanding with keyword matching for better retrieval
- **Three verification capabilities** - Each answer goes through *Grounding* (extract claims, verify them against the retrieved sources), *Accuracy* (a factual-correctness review), and *Quality* (a dual-model developer-experience rating) — distinct checks, not redundant ones
- **Neutral, grounded answers** - The assistant answers only from retrieved documentation, with no product-favorable steering in the prompt; relevant Render docs surface through retrieval, not by being force-sold
- **Cost tracking** - See exactly how much each question costs to answer
- **Concurrent verification** - The Accuracy + dual-model Quality checks run concurrently in-process (via `asyncio.gather`) so they execute in parallel

---

## What This Demonstrates

### Render Capabilities

- **In-process async pipeline** - The 7-stage Q&A pipeline runs in-process inside the FastAPI app as a background asyncio task, with the heavy LLM stages run concurrently via `asyncio.gather`
- **PostgreSQL with pgvector + full-text** - Managed hybrid search database that also stores live per-stage progress and final results
- **Web Service + Static Site** - FastAPI app + Next.js frontend
- **Cron Jobs** - Scheduled ingestion refresh that re-runs the data-driven ingest entrypoint
- **Blueprint deploy + env groups** - `render.yaml` provisions everything; shared config lives in one env group

### Logfire Features

- **LLM Traces** - Complete visibility into every AI call (OpenAI + Anthropic auto-instrumented)
- **HTTP Tracing** - FastAPI auto-instrumentation for request/response tracking
- **Database Monitoring** - AsyncPG auto-instrumentation for query performance
- **Cost Tracking** - Per-stage and per-execution cost attribution with custom metrics
- **Multi-Model Evals** - Dual-rater quality assessment (OpenAI + Anthropic)
- **Session Tracking** - End-to-end user journey with distributed tracing
- **Custom Metrics** - Business-specific metrics (cost, quality, accuracy)
- **SQL Queries** - Custom analytics on AI performance

### Pydantic Stack

This project is built end-to-end on the [Pydantic](https://pydantic.dev/) ecosystem:

- **[Pydantic AI Agents](https://ai.pydantic.dev/agents/)** — every pipeline stage (generation, claims extraction, accuracy check, dual-rater evaluation) is a `pydantic_ai.Agent` with a typed `output_type`. Multi-provider orchestration (Claude + GPT) runs through `OpenAIProvider` / `AnthropicProvider` in a single pipeline. See [`backend/pipeline/`](./backend/pipeline/).
- **[Pydantic Embedder](https://ai.pydantic.dev/embeddings/)** — `pydantic_ai.Embedder` with `OpenAIEmbeddingModel` powers question embedding (`embed_query`) and batch claim embedding (`embed_documents`) for verification. Auto-instrumented by `logfire.instrument_pydantic_ai()`. See [`backend/pipeline/embeddings.py`](./backend/pipeline/embeddings.py) and [`backend/pipeline/verification.py`](./backend/pipeline/verification.py).
- **[Pydantic Models](https://docs.pydantic.dev/)** — Claims, accuracy scores, eval dimensions, and pipeline state are parsed directly into Pydantic models (e.g. `ClaimsOutput`, `EvaluationOutput`). `pydantic-settings` manages config in [`backend/config.py`](./backend/config.py).
- **[Pydantic GenAI Prices](https://github.com/pydantic/genai-prices)** — model pricing is loaded dynamically from the `pydantic/genai-prices` registry, then combined with per-agent token counts from `result.usage()` to produce per-stage cost attribution. See [`backend/prices.py`](./backend/prices.py).
- **[Logfire](https://logfire.pydantic.dev/)** — distributed traces, custom metrics, dual-model evals, and cost attribution. Auto-instruments FastAPI, AsyncPG, HTTPX, and Pydantic AI. See [`backend/observability.py`](./backend/observability.py).

---

## Architecture

The frontend connects to a backend FastAPI app. `POST /ask` launches the 7-stage pipeline as an in-process background asyncio task and returns a `run_id` immediately (HTTP 202); the pipeline writes live per-stage progress and the final result to Postgres, and `GET /ask/{run_id}` polls Postgres for them.

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Next.js + TypeScript)                            │
│  Deployed as: Render Static Site                            │
│  - Question input UI                                        │
│  - Progress via polling (POST /ask → poll GET /ask/{id})    │
│  - Answer display with metrics                              │
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTPS
┌─────────────────────────────────────────────────────────────┐
│  API service (FastAPI + Logfire)                            │
│  Deployed as: Render Web Service (Python 3.13)              │
│  - POST /ask        → launch background task, return run_id │
│  - GET  /ask/{id}   → poll Postgres for progress/result     │
│  - /health, /history, /stats, /sessions/{id}/logs           │
│                                                             │
│  Background asyncio task: run_qa_pipeline (in-process)      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Retrieval  [1] Question Embedding  (OpenAI)            │ │
│  │            [2] RAG Retrieval (pgvector+BM25)           │ │
│  │ Generate   [3] Answer Generation   (Claude)           │ │
│  │ Grounding  [4] Claims Extraction   (GPT)              │ │
│  │            [5] Claims Verification (RAG)              │ │
│  │ Accuracy   [6] Factual-grounding   (Claude) ┐         │ │
│  │ Quality    [7] Dual-model rating   (OpenAI+ ├─ run    │ │
│  │                                    Anthropic)┘ concurrently│
│  │                                    (asyncio.gather)    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
            ↓                                    ↓
┌──────────────────────┐           ┌───────────────────────────┐
│  PostgreSQL          │           │  Logfire                  │
│  (Render Managed)    │           │  (Pydantic)               │
│  - pgvector ext      │           │  - Distributed traces     │
│  - RAG embeddings    │           │  - Cost attribution       │
│  - Full-text search  │           │  - Quality metrics        │
│  - pipeline_progress │           │  - Custom dashboards      │
│  - pipeline_runs     │           └───────────────────────────┘
└──────────────────────┘

  Cron (daily) ─ uv run python data/scripts/ingest_pages.py ─▶ PostgreSQL
```

> **Why this shape?** `POST /ask` returns a `run_id` immediately and the pipeline keeps
> running as a background asyncio task, so the request doesn't block on the full LLM run.
> The task persists live per-stage progress to the `pipeline_progress` table and the final
> result to `pipeline_runs`, which `GET /ask/{run_id}` polls. Stages 6 + 7 (Accuracy + the
> two Quality judges) are independent, so they run concurrently in-process via
> `asyncio.gather`. See [`backend/pipeline/orchestrator.py`](./backend/pipeline/orchestrator.py).

### Project Structure

```
render-qa-assistant/
├── backend/
│   ├── main.py                    # FastAPI app (launches + polls in-process pipeline runs)
│   ├── api/
│   │   └── logs.py                # Logfire logs API endpoint
│   ├── pipeline/                  # 7-stage pipeline implementation (orchestrator.py)
│   ├── ingestion.py               # Shared embed + replace-by-source helpers
│   ├── models.py                  # Pydantic models
│   ├── database.py                # PostgreSQL + pgvector
│   ├── observability.py           # Logfire configuration
│   └── config.py                  # Settings management
├── frontend/
│   ├── src/                       # Next.js + TypeScript UI
│   └── package.json
├── data/
│   ├── embeddings/                # Pre-embedded documentation
│   ├── curated/                   # Hand-curated source content (markdown)
│   ├── sources.py                 # Live-source registry (build strategies + metadata)
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
- PostgreSQL 16+ (with pgvector extension >= 0.5.0, for the HNSW vector index)
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

> **Everything runs locally.** The Q&A pipeline runs in-process inside the FastAPI app, so all
> you need is Postgres running and a `.env` with your API keys. With the database up
> (`make db-start`), `make run-backend` runs `uv run uvicorn backend.main:app`; `POST /ask`
> launches the pipeline as a background task against your local `DATABASE_URL`, so **History**
> populates normally. No Render cloud resources or API key required.

> **Local config → deployed env group.** Locally every process reads one `.env` (copied from
> [`.env.example`](./.env.example)). On deploy that same config lives in the Render env
> group in [`render.yaml`](./render.yaml) — see [Deploy → Environment groups](#environment-groups).
> The Docker `DATABASE_URL` isn't in the group; in the cloud `DATABASE_URL` is injected from the
> database.

`make ingest` runs the full pipeline: bulk doc embeddings, plus the curated "special pages" that get explicit-injection into RAG context (pricing, AI agent, autoscaling, Node.js). These live sources are defined in the [`data/sources.py`](./data/sources.py) registry and ingested through the shared build → embed → replace-by-source helpers. To re-load just one of those after editing its registry entry (or curated content), use the per-target shortcuts:

```bash
make add-pricing      # render.com/pricing tables
make add-ai-agent     # render.com/tutorials/agents-on-render-workflows (AI agents → Render Workflows)
make add-autoscaling  # render.com/docs/scaling
make add-nodejs       # render.com/docs/deploy-node-express-app
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

- PostgreSQL database with pgvector (`pydantic-agents-workflows-db`)
- API web service (`pydantic-agents-workflows-api`, FastAPI + Logfire)
- Ingestion refresh cron (`pydantic-agents-workflows-ingest`, re-runs ingestion daily)
- Frontend static site (`pydantic-agents-workflows-frontend`, Next.js)
- One **environment group** that holds all shared config (see below)

On **Apply**, Render prompts once for the secret values in the env group
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and both Logfire tokens). You fill these at the
**group** level, not per service.

#### Environment groups

`render.yaml` defines one reusable [env group](https://render.com/docs/configure-environment-variables#environment-groups)
so config lives in one place instead of being duplicated across services:

| Group | Contents | Linked to |
|---|---|---|
| **`pydantic-agents-workflows-pipeline`** | LLM/Logfire secrets + all pipeline, RAG, and model config (~20 vars) | API service **and** the ingest cron |

The payoff is `pydantic-agents-workflows-pipeline`: the API service and the ingest cron both run the same
`backend.config.Settings`, so they need identical config — one group keeps them in sync instead of
duplicating ~20 variables. `DATABASE_URL` stays per-service (it's injected from the database, which
can't live in a group), and the frontend's `NEXT_PUBLIC_API_URL` stays inline (unique, build-time).

### 3. Fill in the env-group values

Because the API service and cron read everything from the env group, you set values **on the
group**, not on each service — every linked service picks them up automatically. Set the four
secrets once, when you apply the Blueprint in step 2:

| Variable | Source |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `LOGFIRE_TOKEN` | Logfire write token from step 1 |
| `LOGFIRE_READ_TOKEN` | Logfire read token from step 1 |

The first three are required and the service crashes on startup without them (no defaults in
[`backend/config.py`](./backend/config.py)).

> Edit the group under **Dashboard → Env Groups → `pydantic-agents-workflows-pipeline`**. Saving
> re-deploys every service linked to it, so the API service and cron both pick up changes from a
> single edit.

**Auto-filled, no action needed:** `DATABASE_URL` (injected from the database service) and the
rest of `pydantic-agents-workflows-pipeline`'s config (`MAX_TOKENS`, `TIMEOUT_SECONDS`, `RAG_TOP_K`,
`SIMILARITY_THRESHOLD`, `VERIFICATION_THRESHOLD`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, the
model-selection vars, `ENABLE_CACHING`, `LOG_LEVEL`) ship with sensible defaults in `render.yaml`.

### 4. Wire the frontend to the backend

After the API service deploys, copy its public URL from the service's Dashboard page and set it as
the `NEXT_PUBLIC_API_URL` env var on the **frontend** service, then redeploy the frontend so the
value takes effect. For this deploy that's:

```
NEXT_PUBLIC_API_URL=https://pydantic-agents-workflows-api.onrender.com
```

Use the **base origin only** — no trailing slash and no `/api` path (the frontend appends
`/ask`, `/health`, etc. itself). If your service name isn't globally unique, Render adds a random
suffix (`…-api-xxxx.onrender.com`), so always copy the exact URL shown in the Dashboard.

### 5. Seed the corpus, then done

The database has no documents until ingestion runs. The API service's pre-deploy command seeds it
on first deploy, and the daily cron keeps it fresh. To re-run ingestion on demand, trigger the
`pydantic-agents-workflows-ingest` cron from the Dashboard, which runs:

```bash
uv run python data/scripts/ingest_pages.py
```

### 6. (Optional) Smoke-test the pipeline

Once the corpus is seeded, ask a question from the frontend, or `POST /ask` directly against the
API service and poll `GET /ask/{run_id}`:

```bash
curl -X POST https://pydantic-agents-workflows-api.onrender.com/ask \
  -H 'Content-Type: application/json' \
  -d '{ "question": "How do I deploy an AI agent on Render?" }'
```

## Documentation

### Core Guides

- **[docs/PIPELINE.md](./docs/PIPELINE.md)** - Detailed breakdown of the 7-stage pipeline
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
