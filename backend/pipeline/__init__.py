"""Pipeline modules for the Q&A assistant."""

from .embeddings import embed_question
from .retrieval import retrieve_documents
from .generation import generate_answer
from .claims import extract_claims
from .verification import verify_claims
from .accuracy import check_accuracy
from .evaluation import evaluate_quality
from .quality_gate import quality_gate_decision

__all__ = [
    "embed_question",
    "retrieve_documents",
    "generate_answer",
    "extract_claims",
    "verify_claims",
    "check_accuracy",
    "evaluate_quality",
    "quality_gate_decision",
]

