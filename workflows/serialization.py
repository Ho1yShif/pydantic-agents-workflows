"""JSON (de)serialization helpers for Render Workflows task boundaries.

Render Workflows require task arguments and return values to be
JSON-serializable (max 4 MB per invocation) — no Pydantic/class instances may
cross a task boundary. The rule is: Pydantic objects live *inside* the
``backend.pipeline`` functions; the instant a value crosses an ``@app.task``
boundary it is dumped with ``model_dump(mode="json")``, and re-validated
immediately on the other side.

Keep all the conversions here so the boundary contract lives in one place.
"""

from __future__ import annotations

from typing import Any

from backend.models import Claim, Document


# --- Claims -----------------------------------------------------------------

def claims_to_json(claims: list[Claim]) -> list[dict[str, Any]]:
    """Serialize verified ``Claim`` objects for transport to a subtask."""
    return [c.model_dump(mode="json") for c in claims]


def claims_from_json(data: list[dict[str, Any]]) -> list[Claim]:
    """Rehydrate ``Claim`` objects received as a subtask argument."""
    return [Claim.model_validate(c) for c in data]


# --- Documents --------------------------------------------------------------

def documents_to_json(documents: list[Document]) -> list[dict[str, Any]]:
    """Serialize retrieved ``Document`` objects."""
    return [d.model_dump(mode="json") for d in documents]


def documents_from_json(data: list[dict[str, Any]]) -> list[Document]:
    """Rehydrate ``Document`` objects."""
    return [Document.model_validate(d) for d in data]
