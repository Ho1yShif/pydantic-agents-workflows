# Makefile for Ask Render Anything Assistant
# Simplifies common development tasks

.PHONY: help install dev-setup db-start db-stop db-reset ingest crawl-tutorials embed-tutorials add-pricing add-ai-agent add-autoscaling add-nodejs add-tutorials-index run-backend run-frontend test clean

help:
	@echo "Ask Render Anything Assistant - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       - Install all dependencies (Python + Node)"
	@echo "  make dev-setup     - Complete development setup"
	@echo ""
	@echo "Database:"
	@echo "  make db-start      - Start PostgreSQL with Docker"
	@echo "  make db-stop       - Stop PostgreSQL"
	@echo "  make db-reset      - Reset database (delete all data)"
	@echo "  make ingest        - Generate embeddings and load into database (includes tutorials + all special pages)"
	@echo "  make crawl-tutorials - Preview the render.com/tutorials crawl (no embeddings)"
	@echo "  make embed-tutorials - Embed tutorials into the corpus and sync into the DB"
	@echo "  make add-pricing   - Re-add only the pricing page"
	@echo "  make add-ai-agent  - Re-add only the AI agent answer (Render Workflows tutorial)"
	@echo "  make add-autoscaling - Re-add only the autoscaling docs"
	@echo "  make add-nodejs    - Re-add only the Node.js docs"
	@echo ""
	@echo "Development:"
	@echo "  make run-backend   - Run backend API (port 8000)"
	@echo "  make run-frontend  - Run frontend dev server (port 3000)"
	@echo "  make test          - Run tests"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         - Clean up build artifacts"

install:
	@echo "📦 Installing Python dependencies..."
	uv sync --group dev
	@echo ""
	@echo "📦 Installing Node.js dependencies..."
	cd frontend && npm install
	@echo ""
	@echo "✅ All dependencies installed!"

dev-setup: install
	@echo ""
	@echo "⚙️  Setting up development environment..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "📝 Created .env file from .env.example"; \
		echo "⚠️  Please edit .env and add your API keys!"; \
	else \
		echo "✅ .env file already exists"; \
	fi
	@echo ""
	@echo "🚀 Next steps:"
	@echo "  1. Edit .env and add your API keys"
	@echo "  2. Run: make db-start"
	@echo "  3. Run: make ingest"
	@echo "  4. Run: make run-backend (in one terminal)"
	@echo "  5. Run: make run-frontend (in another terminal)"

db-start:
	@echo "🐘 Starting PostgreSQL with pgvector..."
	docker-compose up -d
	@echo "⏳ Waiting for database to be ready..."
	@sleep 5
	@docker-compose ps
	@echo "✅ Database is running on localhost:5432"

db-stop:
	@echo "🛑 Stopping PostgreSQL..."
	docker-compose down
	@echo "✅ Database stopped"

db-reset:
	@echo "⚠️  This will delete ALL data in the database!"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ]; then \
		docker-compose down -v; \
		docker-compose up -d; \
		echo "✅ Database reset complete"; \
	else \
		echo "❌ Cancelled"; \
	fi

ingest:
	@echo "🔄 Generating embeddings for Render documentation..."
	uv run python data/scripts/generate_embeddings.py
	@echo ""
	@echo "📊 Loading embeddings into database..."
	uv run python data/scripts/ingest_docs.py
	@echo ""
	@echo "🏷️  Adding special pages (pricing, AI agent, autoscaling, Node.js)..."
	uv run python data/scripts/add_pricing_page.py
	uv run python data/scripts/add_workflows_tutorial_page.py
	uv run python data/scripts/add_workflows_docs_page.py
	uv run python data/scripts/add_autoscaling_page.py
	uv run python data/scripts/add_nodejs_page.py
	uv run python data/scripts/add_tutorials_index_page.py
	@echo "✅ Documentation ingested!"

crawl-tutorials:
	@echo "📚 Previewing render.com/tutorials crawl (discovered pages + chunk counts)..."
	uv run python data/scripts/crawl_tutorials.py

embed-tutorials:
	@echo "📚 Embedding render.com/tutorials and merging into the corpus JSON..."
	uv run python data/scripts/embed_tutorials.py
	@echo "📊 Loading new tutorial sources into the database..."
	uv run python data/scripts/ingest_docs.py --sync
	@echo "✅ Tutorials embedded and ingested!"

add-pricing:
	@echo "🏷️  Adding Render pricing page to vector database..."
	@echo "This adds accurate pricing tables for all Render services"
	@echo ""
	uv run python data/scripts/add_pricing_page.py
	@echo "✅ Pricing data added!"

add-ai-agent:
	@echo "🤖 Adding Render Workflows agents tutorial + docs to vector database..."
	@echo "This ensures 'how do I deploy an AI agent on Render?' answers with Workflows"
	@echo ""
	uv run python data/scripts/add_workflows_tutorial_page.py
	uv run python data/scripts/add_workflows_docs_page.py
	@echo "✅ AI agent (Workflows tutorial + docs) context added!"

add-autoscaling:
	@echo "📈 Adding autoscaling documentation to vector database..."
	@echo ""
	uv run python data/scripts/add_autoscaling_page.py
	@echo "✅ Autoscaling docs added!"

add-nodejs:
	@echo "🟩 Adding Node.js deployment documentation to vector database..."
	@echo ""
	uv run python data/scripts/add_nodejs_page.py
	@echo "✅ Node.js docs added!"

add-tutorials-index:
	@echo "📚 Adding render.com/tutorials index recommendation to vector database..."
	@echo ""
	uv run python data/scripts/add_tutorials_index_page.py
	@echo "✅ Tutorials index recommendation added!"

run-backend:
	@echo "🚀 Starting backend API on http://localhost:8000"
	@echo "📖 API docs: http://localhost:8000/docs"
	@echo ""
	uv run uvicorn backend.main:app --reload --port 8000

run-frontend:
	@echo "🎨 Starting frontend on http://localhost:3000"
	@echo ""
	cd frontend && npm run dev

test:
	@echo "🧪 Running tests..."
	uv run pytest backend/tests/ -v

clean:
	@echo "🧹 Cleaning up..."
	rm -rf .venv
	rm -rf frontend/node_modules
	rm -rf frontend/.next
	rm -rf frontend/out
	rm -rf backend/__pycache__
	rm -rf backend/**/__pycache__
	rm -rf .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "✅ Cleanup complete"

