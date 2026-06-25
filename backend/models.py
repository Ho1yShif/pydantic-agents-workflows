"""Pydantic models for the Q&A pipeline."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import re
import html


# ---------------------------------------------------------------------------
# Intermediate structured output models for pydantic-ai agents
# ---------------------------------------------------------------------------

class QueryExpansionOutput(BaseModel):
    """Structured output for query expansion agent."""
    queries: list[str] = Field(..., description="Alternative query phrasings")


class ClaimsOutput(BaseModel):
    """Structured output for claims extraction agent."""
    claims: list[str] = Field(..., description="Extracted factual claims")


class AccuracyOutput(BaseModel):
    """Structured output for technical accuracy agent."""
    accuracy_score: int = Field(..., ge=0, le=100, description="Accuracy score (0-100)")
    errors: list[str] = Field(default_factory=list, description="Technical errors found")
    corrections: list[str] = Field(default_factory=list, description="Suggested corrections")


class EvaluationOutput(BaseModel):
    """Structured output for quality evaluation agents."""
    technical_accuracy: int = Field(..., ge=0, le=100)
    clarity: int = Field(..., ge=0, le=100)
    completeness: int = Field(..., ge=0, le=100)
    developer_value: int = Field(..., ge=0, le=100)
    overall: int = Field(..., ge=0, le=100)
    feedback: str


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    """Request model for asking a question."""

    question: str = Field(..., min_length=10, max_length=500, description="The question to answer")
    session_id: Optional[str] = Field(None, description="Optional session ID for conversation tracking")

    @field_validator('question', mode='before')
    @classmethod
    def sanitize_question(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("question must be a string")
        # Strip null bytes and non-printable control characters (keep \n \t \r)
        v = re.sub(r'[\x00\x01-\x08\x0B\x0C\x0E-\x1F\x7F]', '', v)
        # Decode HTML entities before stripping tags to prevent bypass via &lt;script&gt;
        v = html.unescape(v)
        # Strip HTML tags
        v = re.sub(r'<[^>]*>', '', v)
        # Strip orphaned angle brackets that survived tag stripping
        v = re.sub(r'[<>]', '', v)
        # Collapse 3+ consecutive newlines to 2
        v = re.sub(r'\n{3,}', '\n\n', v)
        return v.strip()


class Document(BaseModel):
    """A retrieved document from the RAG system."""
    
    content: str = Field(..., description="The document content")
    source: str = Field(..., description="Source URL or reference")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class Claim(BaseModel):
    """A factual claim extracted from the answer."""
    
    claim: str = Field(..., description="The claim text")
    verified: bool = Field(False, description="Whether the claim was verified")
    verification_score: float = Field(0.0, ge=0.0, le=1.0, description="Verification confidence")
    supporting_docs: list[str] = Field(default_factory=list, description="Supporting document references")


class EvaluationResult(BaseModel):
    """Result from a single evaluator."""
    
    model: str = Field(..., description="Model that performed the evaluation")
    score: int = Field(..., ge=0, le=100, description="Quality score (0-100)")
    technical_accuracy: int = Field(..., ge=0, le=100, description="Technical accuracy score")
    clarity: int = Field(..., ge=0, le=100, description="Clarity score")
    completeness: int = Field(..., ge=0, le=100, description="Completeness score")
    developer_value: int = Field(..., ge=0, le=100, description="Developer value score")
    feedback: str = Field(..., description="Detailed feedback")


class PipelineStageResult(BaseModel):
    """Result from a single pipeline stage."""
    
    stage: str = Field(..., description="Stage name")
    success: bool = Field(..., description="Whether the stage succeeded")
    duration_ms: float = Field(..., description="Stage duration in milliseconds")
    cost_usd: float = Field(0.0, description="Stage cost in USD")
    tokens_used: Optional[int] = Field(None, description="Tokens used")
    model: Optional[str] = Field(None, description="Model used for this stage")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[dict] = Field(None, description="Stage-specific metadata")


class AnswerResponse(BaseModel):
    """Final response model."""
    
    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="The generated answer")
    sources: list[Document] = Field(default_factory=list, description="Source documents")
    claims: list[Claim] = Field(default_factory=list, description="Extracted claims")
    quality_score: float = Field(..., ge=0, le=100, description="Overall quality score")
    accuracy_score: float = Field(0, ge=0, le=100, description="Technical accuracy score")
    evaluations: list[EvaluationResult] = Field(default_factory=list, description="Evaluator results")
    iterations: int = Field(1, description="Number of refinement iterations")
    total_cost: float = Field(0.0, description="Total cost in USD")
    total_duration_ms: float = Field(..., description="Total pipeline duration")
    stages: list[PipelineStageResult] = Field(default_factory=list, description="Individual stage results")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    session_id: Optional[str] = Field(None, description="Session ID if provided")


class ProgressUpdate(BaseModel):
    """Server-sent event for progress tracking."""
    
    stage: str = Field(..., description="Current stage name")
    status: str = Field(..., description="Status: 'started', 'completed', 'failed'")
    message: str = Field(..., description="Human-readable message")
    progress: float = Field(..., ge=0, le=100, description="Overall progress percentage")
    cost_so_far: float = Field(0.0, description="Accumulated cost")
    duration_ms: Optional[float] = Field(None, description="Stage duration if completed")


class HealthCheck(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status")
    database_connected: bool = Field(..., description="Database connection status")
    logfire_enabled: bool = Field(..., description="Logfire instrumentation status")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentChunk(BaseModel):
    """A chunk of documentation for ingestion."""
    
    content: str = Field(..., description="The chunk content")
    source: str = Field(..., description="Source URL")
    title: str = Field(..., description="Document title")
    section: Optional[str] = Field(None, description="Section within the document")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class IngestionRequest(BaseModel):
    """Request to ingest documentation."""
    
    chunks: list[DocumentChunk] = Field(..., description="Document chunks to ingest")
    batch_size: int = Field(100, ge=1, le=1000, description="Batch size for processing")


class IngestionResponse(BaseModel):
    """Response from document ingestion."""
    
    success: bool = Field(..., description="Whether ingestion succeeded")
    chunks_processed: int = Field(..., description="Number of chunks processed")
    duration_ms: float = Field(..., description="Processing duration")
    cost_usd: float = Field(..., description="Total cost")
    errors: list[str] = Field(default_factory=list, description="Any errors encountered")

