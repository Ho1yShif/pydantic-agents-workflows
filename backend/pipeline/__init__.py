"""Pipeline modules for the Q&A assistant."""

from .embeddings import embed_question
from .retrieval import retrieve_documents, collapse_sources
from .generation import generate_answer
from .claims import extract_claims
from .verification import verify_claims
from .accuracy import check_accuracy

__all__ = [
    "embed_question",
    "retrieve_documents",
    "collapse_sources",
    "generate_answer",
    "extract_claims",
    "verify_claims",
    "check_accuracy",
]

