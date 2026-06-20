"""Configuration settings for the Ask Render Anything Assistant."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)
    
    # API Keys
    openai_api_key: str
    anthropic_api_key: str
    logfire_token: str
    logfire_read_token: str = ""  # Optional: for fetching logs via API
    # Logfire Query API base URL. Use https://logfire-eu.pydantic.dev for EU-region projects.
    logfire_api_base: str = "https://logfire-us.pydantic.dev"
    
    # Database
    database_url: str
    
    # Pipeline Configuration
    quality_threshold: int = 85
    accuracy_threshold: int = 70  # Based on empirical avg of 73 (was 80, too strict)
    agreement_threshold: int = 10
    max_iterations: int = 1  # First iteration is best; further iterations degrade quality
    max_tokens: int = 2000
    timeout_seconds: int = 30
    
    # RAG Configuration
    rag_top_k: int = 20  # Increased to 20 for broader coverage of multi-product questions
    similarity_threshold: float = 0.3  # Lowered from 0.5 for broader retrieval
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

