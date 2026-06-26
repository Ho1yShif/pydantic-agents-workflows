"""Configuration settings for the Ask Render Anything Assistant."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    # extra="ignore": tolerate SDK-only env vars that live in the shared .env but aren't
    # Settings fields (e.g. RENDER_USE_LOCAL_DEV / RENDER_LOCAL_DEV_URL for local dev, and the
    # platform-injected RENDER_SDK_MODE / RENDER_SDK_SOCKET_PATH). Without this, pydantic-settings
    # defaults to extra="forbid" and crashes on startup when those keys appear in the .env file.
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")
    
    # API Keys
    openai_api_key: str
    anthropic_api_key: str
    logfire_token: str
    logfire_read_token: str = ""  # Optional: for fetching logs via API
    # Logfire Query API base URL. Use https://logfire-eu.pydantic.dev for EU-region projects.
    logfire_api_base: str = "https://logfire-us.pydantic.dev"
    
    # Database
    database_url: str

    # Render Workflows (gateway -> workflow service)
    render_api_key: str = ""  # Required to trigger/poll workflow runs
    workflow_slug: str = ""  # e.g. "pydantic-agents-pipeline" (from the Workflow's Dashboard page)
    
    # Pipeline Configuration
    quality_threshold: int = 85
    accuracy_threshold: int = 70  # Based on empirical avg of 73 (was 80, too strict)
    agreement_threshold: int = 10
    max_iterations: int = 1  # First iteration is best; further iterations degrade quality
    max_tokens: int = 4000  # Answer generation budget; raised from 2000 so broad answers aren't truncated
    timeout_seconds: int = 30
    
    # RAG Configuration
    rag_top_k: int = 20  # Ceiling on retrieved docs, not a fixed quota (see hybrid_search)
    # Real relevance gate: a doc is returned only if its cosine similarity >= this value,
    # so the result count varies with the question. Tune up (~0.4-0.5) if broad questions
    # still return too many low-relevance docs; down if narrow questions return too few.
    similarity_threshold: float = 0.3
    verification_threshold: float = 0.30  # Similarity threshold for claim verification (lowered to catch explicit facts)
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    
    # Model Selection
    answer_model: str = "claude-sonnet-4-6"
    claims_model: str = "gpt-5.4-mini"
    accuracy_model: str = "claude-sonnet-4-6"
    eval_model_openai: str = "gpt-5.4-mini"
    eval_model_anthropic: str = "claude-sonnet-4-6"
    query_expansion_model: str = "gpt-4.1-nano"
    
    # Performance
    enable_caching: bool = True
    log_level: str = "INFO"
    
    # CORS
    cors_origins: list[str] = ["*"]


class PipelineConfig:
    """Static pipeline configuration constants."""

    # Stage names for tracing
    STAGE_EMBEDDING = "question_embedding"
    STAGE_RETRIEVAL = "rag_retrieval"
    STAGE_GENERATION = "answer_generation"
    STAGE_CLAIMS = "claims_extraction"
    STAGE_VERIFICATION = "claims_verification"
    STAGE_ACCURACY = "technical_accuracy"
    STAGE_EVALUATION = "quality_evaluation"
    STAGE_QUALITY_GATE = "quality_gate"


# Global settings instance
settings = Settings()

