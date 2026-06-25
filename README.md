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
2. **Watch the pipeline** - Track progress as the run moves through 8 stages (embedding → retrieval → generation → verification)
3. **Get accurate answers** - Receive detailed responses with sources from Render docs
4. **Quality guaranteed** - Every answer is verified for accuracy and rated by dual AI evaluators

### Key Features

- **Hybrid search** - Combines semantic understanding with keyword matching for better retrieval
- **Multi-stage verification** - Extracts claims, verifies against docs, checks technical accuracy
- **Iterative refinement** - Automatically regenerates low-quality answers with feedback
- **Cost tracking** - See exactly how much each question costs to answer
- **Parallel fan-out** - The pipeline runs on [Render Workflows](https://render.com/docs/workflows), fanning out the heaviest stages (technical accuracy + dual-model evaluation) across instances so they execute concurrently

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
- **Render Workflows** - The Q&A pipeline and ingestion run as durable workflow tasks with per-task retries, timeouts, and cross-instance parallel fan-out
- **Web Service + Static Site** - FastAPI gateway + Next.js frontend
- **Cron Jobs** - Scheduled ingestion refresh that triggers the workflow fan-out
- **Environment Management** - Secure secrets handling
- **Auto-Scaling** - Handle variable AI workloads

---

## Architecture

The pipeline no longer runs inside the web service. The web service is now a **thin
FastAPI gateway** that triggers a **Render Workflows** run and polls it for the result;
the 8-stage pipeline and ingestion execute as workflow tasks that fan out across instances.

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
│  API Gateway (FastAPI + Logfire)                            │
│  Deployed as: Render Web Service (Python 3.13)              │
│  - POST /ask        → start_task("…/run_qa_pipeline")       │
│  - GET  /ask/{id}   → get_task_run(id) (poll status/result) │
│  - /health, /history, /stats, /sessions/{id}/logs           │
└─────────────────────────────────────────────────────────────┘
            ↓ Render SDK (start_task / get_task_run)
┌─────────────────────────────────────────────────────────────┐
│  Render Workflows service  (Python 3.13)                    │
│  Orchestrator: run_qa_pipeline                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [1] Question Embedding      (OpenAI)        in-process  │ │
│  │ [2] RAG Document Retrieval  (pgvector+BM25) in-process  │ │
│  │ [3] Answer Generation       (Claude)        ⟶ subtask   │ │
│  │ [4] Claims Extraction       (GPT)           ⟶ subtask   │ │
│  │ [5] Claims Verification     (RAG again)     ⟶ subtask   │ │
│  │ [6] Technical Accuracy      (Claude)    ┐               │ │
│  │ [7] Quality Rating          (OpenAI+    ├─ 3 parallel   │ │
│  │                              Anthropic) ┘   subtasks    │ │
│  │ [8] Quality Gate            (Pass or Iterate) in-process │ │
│  └────────────────────────────────────────────────────────┘ │
│  Ingestion: ingest_all → ingest_core, then 6 add_* in       │
│             parallel (replaces the old serial preDeploy)    │
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

  Cron (daily) ─ start_task("…/ingest_all") ─▶ Workflows service
```

> **Why hybrid?** Workflows aren't HTTP-facing, so a client (the gateway) triggers tasks
> via the SDK and reads run status. Stages 1, 2, and 8 are cheap/data-dependent and stay
> in-process on the orchestrator; only the heavy, independently-retryable LLM stages are
> promoted to their own tasks. Stages 6 + 7 run as three concurrent subtasks on separate
> instances. See [`workflows/app.py`](./workflows/app.py).

### Project Structure

```
render-qa-assistant/
├── backend/
│   ├── main.py                    # FastAPI gateway (triggers + polls workflow runs)
│   ├── api/
│   │   └── logs.py                # Logfire logs API endpoint
│   ├── pipeline/                  # 8-stage pipeline implementation (reused by workflows)
│   ├── models.py                  # Pydantic models
│   ├── database.py                # PostgreSQL + pgvector
│   ├── observability.py           # Logfire configuration
│   └── config.py                  # Settings management
├── workflows/                     # Render Workflows service
│   ├── app.py                     # Workflows() instance + all @app.task defs
│   ├── serialization.py           # JSON boundary helpers (model_dump/model_validate)
│   └── trigger_ingest.py          # Cron entrypoint → start_task("…/ingest_all")
├── frontend/
│   ├── src/                       # Next.js + TypeScript UI
│   └── package.json
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

> **Asking questions locally needs the Workflows runtime running too.** The backend is a thin
> gateway — `POST /ask` delegates to a Workflows service. With nothing to delegate to it returns
> `503 WORKFLOW_SLUG is not configured`. You can run the whole stack locally with **no Render
> cloud resources and no API key** — the pipeline runs on your machine against your local
> Postgres:
>
> ```bash
> # Terminal 1 — local workflow dev server (loads .env, listens on :8120)
> render workflows dev -- uv run render-workflows workflows.app:app
>
> # Terminal 2 — gateway pointed at the local dev server
> RENDER_USE_LOCAL_DEV=true WORKFLOW_SLUG=local \
>   uv run uvicorn backend.main:app --reload --port 8000
>
> # Terminal 3 — frontend
> cd frontend && npm run dev
> ```
>
> `RENDER_USE_LOCAL_DEV=true` makes the SDK target `http://localhost:8120` (the dev server)
> instead of Render's cloud, with no token required. `WORKFLOW_SLUG=local` can be any non-empty
> value — it just satisfies the gateway's guard; the dev server resolves the task by name. Set
> both in your `.env` to avoid prefixing each command. Because the workflow runs locally against
> the same `DATABASE_URL`, the **History** tab populates normally.
>
> *(Alternatively, point the local gateway at a deployed cloud Workflows service by setting
> `RENDER_API_KEY` + the real `WORKFLOW_SLUG` instead of `RENDER_USE_LOCAL_DEV`. In that case the
> cloud workflow writes to its own database, so local History only matches if the gateway uses
> that same database.)*

> **Local config → deployed env groups.** Locally, every process reads from one `.env`
> (copied from [`.env.example`](./.env.example)). When you deploy, that same `.env` splits into
> the two Render env groups in [`render.yaml`](./render.yaml): the LLM/Logfire secrets +
> pipeline/RAG/model config become **`pydantic-agents-workflows-pipeline`**, and `RENDER_API_KEY` / `WORKFLOW_SLUG`
> become **`pydantic-agents-workflows-pipeline-trigger`**. So editing `.env` is the local equivalent of editing a group —
> see [Deploy → Environment groups](#environment-groups). The local-only knobs
> (`RENDER_USE_LOCAL_DEV`, `DATABASE_URL` pointing at Docker Postgres) don't go in any group:
> in the cloud the SDK uses the platform socket and `DATABASE_URL` is injected from the database.

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

# 5. Run backend gateway (from project root)
uv run uvicorn backend.main:app --reload --port 8000

# 6. Run frontend (separate terminal)
cd frontend && npm install && npm run dev
```

> **Note:** asking questions through the UI also needs the Workflows runtime running (e.g.
> `render workflows dev …` with `RENDER_USE_LOCAL_DEV=true`) — see
> [the local-workflows note above](#local-development-with-make).

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
- API gateway web service (`pydantic-agents-workflows-api`, FastAPI + Logfire)
- Ingestion refresh cron (`pydantic-agents-workflows-ingest`, triggers the workflow daily)
- Frontend static site (`pydantic-agents-workflows-frontend`, Next.js)
- Two **environment groups** that hold all shared config (see below)

On **Apply**, Render prompts once for the secret values in the env groups
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, both Logfire tokens, and — left blank for now —
`RENDER_API_KEY` / `WORKFLOW_SLUG`). You fill these at the **group** level, not per service.

#### Environment groups

`render.yaml` defines two reusable [env groups](https://render.com/docs/configure-environment-variables#environment-groups)
so config lives in one place instead of being duplicated across services:

| Group | Contents | Linked to |
|---|---|---|
| **`pydantic-agents-workflows-pipeline`** | LLM/Logfire secrets + all pipeline, RAG, and model config (~20 vars) | API gateway **and** the Workflows service (step 3) |
| **`pydantic-agents-workflows-pipeline-trigger`** | `RENDER_API_KEY`, `WORKFLOW_SLUG` | API gateway **and** the ingest cron |

The payoff is `pydantic-agents-workflows-pipeline`: the gateway and the Workflows service both run the same
`backend.config.Settings`, so they need identical config. Linking the group to the
hand-created Workflows service (step 3) replaces pasting ~20 variables by hand. `DATABASE_URL`
stays per-service (it's injected from the database, which can't live in a group), and the
frontend's `NEXT_PUBLIC_API_URL` stays inline (unique, build-time).

> **Note:** Blueprints (`render.yaml`) don't yet support Render Workflows, so the
> **Workflows service** that runs the pipeline is created separately in step 3.

### 3. Create the Workflows service

Blueprints (`render.yaml`) can't create Workflows yet, so do this once in the Dashboard.

**3a. Open the create form.** In the [Render Dashboard](https://dashboard.render.com), click
**New → Workflow**. Connect this GitHub repo (or your fork) when prompted.

**3b. Fill in every field exactly as below:**

| Field | Value |
|---|---|
| **Name** | `pydantic-agents-workflow` (this becomes the workflow slug) |
| **Project / Environment** | Same project + `production` environment as the rest of the stack |
| **Language / Runtime** | `Python 3` |
| **Branch** | `main` (or the branch you deploy) |
| **Region** | `Oregon` (must match `pydantic-agents-workflows-db`) |
| **Root Directory** | *(leave blank — the repo root)* |
| **Build Command** | `pip install uv && uv sync --no-dev --frozen` |
| **Start Command** | `uv run render-workflows workflows.app:app` |
| **Instance Type** | `Standard` (the tasks are I/O-bound; no need for Pro) |

> **`uv: command not found`?** A hand-created Workflow service doesn't get `uv` pre-installed
> (unlike Blueprint services), so the build command installs it first with `pip install uv`.
>
> **Pin Python to 3.13.** The build may default to a newer Python (e.g. 3.14) and ignore the
> repo's `.python-version`. Add an env var **`PYTHON_VERSION` = `3.13`** in step 3c so the build
> matches `uv.lock` and the rest of the stack.

**3c. Link config and add the database.** The Workflows service runs the same
`backend.config.Settings` as the gateway, so instead of re-typing every variable, **link the
`pydantic-agents-workflows-pipeline` env group** the Blueprint already created:

1. Under **Environment → Environment Groups**, click **Link Existing Group → `pydantic-agents-workflows-pipeline`**.
   This pulls in both API keys, both Logfire tokens, and all pipeline/RAG/model config in one step.
2. Add the two variables that *can't* come from the group (env groups hold only plain
   `key: value` pairs — no database links):

   | Variable | Required? | Value / Source |
   |---|---|---|
   | `DATABASE_URL` | ✅ Required | Click **Add from Database → `pydantic-agents-workflows-db`** (already provisioned by step 2's Blueprint — you are *not* creating a new database, just linking the existing one). Use the **same** database as the gateway so the **History** tab populates. |
   | `PYTHON_VERSION` | Recommended | `3.13` (see the build note above) |

   > **Bind `DATABASE_URL`, don't hardcode it.** *Add from Database* injects the managed
   > internal connection string and auto-updates if creds rotate. Pasting a literal URL (into the
   > service or the group) is a static snapshot that breaks on rotation — avoid it.

The four secrets in `pydantic-agents-workflows-pipeline` (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LOGFIRE_TOKEN`,
`LOGFIRE_READ_TOKEN`) are **required** — the service crashes on startup without the first three
(they have no defaults in [`backend/config.py`](./backend/config.py)). You set them once when
applying the Blueprint (step 2); linking the group here reuses those same values.

**End state — the Workflows service environment:**

```
[linked group]  pydantic-agents-workflows-pipeline   # 4 secrets + pipeline/RAG/model config
DATABASE_URL    → from pydantic-agents-workflows-db   # per-service bind, not in any group
PYTHON_VERSION  = 3.13
```

> **Don't link `pydantic-agents-workflows-pipeline-trigger` to the Workflows service.** `RENDER_API_KEY` / `WORKFLOW_SLUG`
> are only for the gateway/cron that *trigger* it from outside. The workflow fans out its own
> subtasks over the platform-injected socket, so it never calls the public API. Likewise, leave
> the platform-injected `RENDER_SDK_MODE` / `RENDER_SDK_SOCKET_PATH` alone.

**3d. Create the service** and wait for the first deploy to finish. Then copy the service's
**slug** (shown on its Dashboard page / in its URL, e.g. `pydantic-agents-workflow`) — you'll
set it as `WORKFLOW_SLUG` in the `pydantic-agents-workflows-pipeline-trigger` group in step 4, which the gateway and cron
both inherit.

### 4. Fill in the env-group values

Because the gateway and cron read everything from the two env groups, you set values **on the
groups**, not on each service — every linked service picks them up automatically.

**`pydantic-agents-workflows-pipeline`** (drives the gateway + Workflows service) — set the four secrets once, when
you apply the Blueprint in step 2:

| Variable | Source |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `LOGFIRE_TOKEN` | Logfire write token from step 1 |
| `LOGFIRE_READ_TOKEN` | Logfire read token from step 1 |

**`pydantic-agents-workflows-pipeline-trigger`** (shared by the gateway + cron) — set these after the Workflows service
exists (step 3):

| Variable | Source |
|---|---|
| `RENDER_API_KEY` | [Render Account Settings → API Keys](https://dashboard.render.com/settings#api-keys) |
| `WORKFLOW_SLUG` | The Workflows service slug from step 3 (e.g. `pydantic-agents-workflow`) |

> Edit a group under **Dashboard → Env Groups → `<group>`**. Saving re-deploys every service
> linked to it, so the gateway and cron both pick up `WORKFLOW_SLUG` from a single edit.

**Auto-filled, no action needed:** `DATABASE_URL` (injected from the database service) and the
rest of `pydantic-agents-workflows-pipeline`'s config (`QUALITY_THRESHOLD`, `ACCURACY_THRESHOLD`, `AGREEMENT_THRESHOLD`,
`MAX_ITERATIONS`, `MAX_TOKENS`, `TIMEOUT_SECONDS`, `RAG_TOP_K`, `SIMILARITY_THRESHOLD`,
`VERIFICATION_THRESHOLD`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, the model-selection vars,
`ENABLE_CACHING`, `LOG_LEVEL`) ship with sensible defaults in `render.yaml`.

### 5. Wire the frontend to the backend

After the gateway deploys, copy its public URL (`https://pydantic-agents-workflows-api-XXXX.onrender.com`) and set it as the `NEXT_PUBLIC_API_URL` env var on the **frontend** service. Trigger a redeploy of the frontend so the new value takes effect.

### 6. Seed the corpus, then done

The Workflows service has no documents until ingestion runs. Trigger it once to seed the DB
(the cron will keep it fresh afterward):

```bash
render workflows start ingest_all   # or trigger from the Dashboard
```

- Gateway: `https://pydantic-agents-workflows-api-XXXX.onrender.com`
- Frontend: `https://pydantic-agents-workflows-frontend-XXXX.onrender.com`

Ingestion now runs as the `ingest_all` workflow task instead of a `preDeployCommand`. It loads
the bulk corpus first (`ingest_core`), then fans out the curated special pages
(`add_pricing`, `add_workflows_tutorial`, `add_workflows_docs`, `add_autoscaling`, `add_nodejs`,
`add_tutorials_index`) in parallel. The `pydantic-agents-workflows-ingest` cron re-triggers it daily so
canonical answers stay in sync with the latest source pages.

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
