"""Service layer: parse -> redact -> normalize -> analyze. Independent of HTTP."""

from __future__ import annotations

import time

from .analysis.engine import analyze_events
from .config import DEFAULT_LIMITS, Limits
from .errors import EmptyInputError, InputTooLargeError
from .llm import HypothesisEnricher
from .models import AnalysisResponse, IngestStats
from .normalization import normalize_records
from .parsing import parse_logs
from .redaction import redact_records, redact_text


def analyze_text(
    content: str,
    *,
    format_hint: str = "auto",
    limits: Limits = DEFAULT_LIMITS,
    enricher: HypothesisEnricher | None = None,
    timings: dict[str, float] | None = None,
) -> AnalysisResponse:
    """Analyze raw log text. Raises IncidentLensError subclasses for rejected input.

    The content is processed in memory only; nothing is written to disk or sent anywhere.
    If ``timings`` is given, per-stage wall-clock seconds are recorded in it (used by the benchmark).
    """
    clock = time.perf_counter
    t = clock()

    def lap(name: str) -> None:
        nonlocal t
        now = clock()
        if timings is not None:
            timings[name] = now - t
        t = now

    if not content or not content.strip():
        raise EmptyInputError("No log content was provided.")
    size = len(content.encode("utf-8", errors="replace"))
    if size > limits.max_input_bytes:
        raise InputTooLargeError(
            f"Input is {size:,} bytes; the limit is {limits.max_input_bytes:,} bytes."
        )

    parsed = parse_logs(content, format_hint, limits)
    lap("parse")
    redactions = redact_records(parsed.records)
    samples = parsed.malformed[: limits.max_malformed_samples]
    for m in samples:
        m.sample = redact_text(m.sample, redactions)
    lap("redact")

    stats = IngestStats(
        detected_format=parsed.format,
        input_bytes=size,
        total_records=len(parsed.records) + len(parsed.malformed),
        parsed_records=len(parsed.records),
        malformed_records=len(parsed.malformed),
        malformed_samples=samples,
        redactions=dict(sorted(redactions.items())),
        warnings=list(parsed.warnings),
    )
    if parsed.malformed:
        stats.warnings.append(f"{len(parsed.malformed)} record(s) could not be parsed and were skipped.")
    events = normalize_records(parsed.records, stats, limits)
    lap("normalize")
    result = analyze_events(events, stats, limits)
    lap("analyze")
    return enricher.enrich(result) if enricher else result
