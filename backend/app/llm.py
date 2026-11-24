"""Extension point for a future, optional LLM integration.

Not used by the MVP: no external calls are made and no API key is read. A future enricher
would receive only the structured, already-redacted AnalysisResponse (never raw input) and
return an annotated copy. Deterministic hypotheses must remain the source of truth.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import AnalysisResponse


@runtime_checkable
class HypothesisEnricher(Protocol):
    name: str

    def enrich(self, response: AnalysisResponse) -> AnalysisResponse:
        """Return an annotated copy of ``response``. Must not mutate the input."""
        ...


class NullEnricher:
    """Default no-op enricher."""

    name = "none"

    def enrich(self, response: AnalysisResponse) -> AnalysisResponse:
        return response
