"""Orchestrates the analysis stages and assembles an AnalysisResponse."""

from __future__ import annotations

from collections import Counter

from .. import __version__
from ..config import DEFAULT_LIMITS, Limits
from ..models import (
    SEVERITY_RANK, AnalysisResponse, CascadeFinding, Hypothesis, IncidentSeverity, IngestStats,
    LogEvent, RecommendedStep, ServiceSummary, Severity, Spike, Summary, TimeRange, Verdict,
)
from .correlation import detect_cascade, pairwise_correlations
from .grouping import exception_patterns, group_events
from .hypotheses import evaluate
from .timeline import build_timeline, detect_spikes, is_error

MIN_EVENTS_FOR_ANALYSIS = 5
NOISE_RATIO = 0.01
_ORDER = ["none", "low", "medium", "high", "critical"]


def assess_severity(
    total: int, errors: int, criticals: int, spikes: list[Spike], cascade: CascadeFinding | None
) -> tuple[IncidentSeverity, list[str]]:
    """Documented, deterministic incident-severity rules (see docs/ARCHITECTURE.md)."""
    if total == 0 or errors == 0:
        return "none", ["No ERROR or CRITICAL events were found."]
    ratio = errors / total
    if not spikes and cascade is None and criticals == 0 and ratio < NOISE_RATIO:
        return "none", [
            f"{errors} error event(s) ({ratio:.2%} of events) with no spike, no cascade and no CRITICAL events: within routine noise."
        ]
    level, reasons = 1, [f"{errors} error event(s) ({ratio:.1%} of {total} events)."]

    def raise_to(n: int, why: str) -> None:
        nonlocal level
        level = max(level, n)
        reasons.append(why)

    if spikes:
        raise_to(2, f"{len(spikes)} error spike(s) detected.")
    if ratio >= 0.05:
        raise_to(2, "Error ratio is at least 5%.")
    if ratio >= 0.15:
        raise_to(3, "Error ratio is at least 15%.")
    if criticals and spikes:
        raise_to(3, f"{criticals} CRITICAL event(s) during a spike.")
    if ratio >= 0.30:
        raise_to(4, "Error ratio is at least 30%.")
    if cascade is not None:
        raise_to(4, f"Failures cascaded across {len(cascade.steps)} services.")
    return _ORDER[level], reasons  # type: ignore[return-value]


def _steps(
    hyps: list[Hypothesis], cascade: CascadeFinding | None, spikes: list[Spike], top_group: str | None
) -> list[RecommendedStep]:
    out: list[RecommendedStep] = []

    def add(text: str, source: str) -> None:
        out.append(RecommendedStep(priority=len(out) + 1, text=text, source=source))

    if spikes:
        s = spikes[0]
        add(f"Start with the first error spike ({s.start:%H:%M:%S}-{s.end:%H:%M:%S} UTC): check deploys, config changes and traffic changes around {s.start:%H:%M:%S}.", "spike")
    if cascade:
        add(f"Investigate {', '.join(cascade.origin_services)} first: it was the first to show errors; later services failed in waves after it.", "cascade")
    for h in hyps[:3]:
        for action in h.recommended_actions[:2]:
            add(f"[{h.title}] {action}", f"hypothesis:{h.category}")
    if top_group:
        add(f"Search for the most frequent error pattern in your tracing/log tool: \"{top_group[:120]}\".", "error_group")
    return out


def _select_events(events: list[LogEvent], cap: int) -> tuple[list[LogEvent], bool]:
    if len(events) <= cap:
        return events, False
    notable = [e for e in events if SEVERITY_RANK[e.severity] >= SEVERITY_RANK[Severity.WARNING]]
    if len(notable) >= cap:
        chosen = sorted(notable, key=lambda e: (-SEVERITY_RANK[e.severity], e.id))[:cap]
    else:
        others = [e for e in events if SEVERITY_RANK[e.severity] < SEVERITY_RANK[Severity.WARNING]]
        room = cap - len(notable)
        # Evenly spaced sample of the remaining (INFO/DEBUG) events, exactly ``room`` of them.
        sampled = [others[i * len(others) // room] for i in range(room)] if room else []
        chosen = notable + sampled
    chosen.sort(key=lambda e: e.id)
    return chosen, True


def analyze_events(events: list[LogEvent], ingest: IngestStats, limits: Limits = DEFAULT_LIMITS) -> AnalysisResponse:
    total = len(events)
    sev_counts = Counter(e.severity.value for e in events)
    distribution = {s.value: sev_counts.get(s.value, 0) for s in Severity}
    errors = distribution["ERROR"] + distribution["CRITICAL"]
    criticals = distribution["CRITICAL"]

    per_service: dict[str, list[int]] = {}
    for e in events:
        row = per_service.setdefault(e.service, [0, 0, 0])
        row[0] += 1
        row[1] += is_error(e)
        row[2] += e.severity == Severity.WARNING
    services = [
        ServiceSummary(name=n, events=r[0], errors=r[1], warnings=r[2])
        for n, r in sorted(per_service.items(), key=lambda kv: (-kv[1][1], -kv[1][2], -kv[1][0], kv[0]))
    ]

    buckets, bucket_seconds, index = build_timeline(events)
    spikes = detect_spikes(events, buckets, index)
    stamps = [e.timestamp for e in events if e.timestamp is not None]
    lo, hi = (min(stamps), max(stamps)) if stamps else (None, None)  # type: ignore[type-var]
    span = (hi - lo).total_seconds() if lo and hi else 0.0
    cascade = detect_cascade(events, bucket_seconds, span) if stamps else None
    correlations = pairwise_correlations(events, len(buckets), index, bucket_seconds)
    groups = group_events(events)
    patterns = exception_patterns(events, index if buckets else None)

    severity, reasons = assess_severity(total, errors, criticals, spikes, cascade)
    hypotheses: list[Hypothesis] = []
    if total < MIN_EVENTS_FOR_ANALYSIS:
        verdict: Verdict = "insufficient_evidence"
        reason = f"Only {total} event(s) were parsed; at least {MIN_EVENTS_FOR_ANALYSIS} are needed for a meaningful analysis."
        severity, reasons = "none", [reason]
    elif severity == "none":
        verdict = "no_incident"
        reason = "Error activity is absent or within routine noise, so no root-cause hypotheses were generated."
    else:
        hypotheses = evaluate(events, spikes, errors)
        if hypotheses:
            verdict = "incident_detected"
            reason = f"{len(hypotheses)} hypothesis(es) ranked by heuristic evidence score; the top one is '{hypotheses[0].title}'."
        else:
            verdict = "insufficient_evidence"
            reason = (
                "Error activity was detected, but no known failure pattern had enough supporting evidence "
                f"(need at least {3} matching events including {2} errors). Review the error groups manually."
            )

    selected, truncated = _select_events(events, limits.max_returned_events)
    summary = Summary(
        total_events=total, error_count=errors, critical_count=criticals,
        warning_count=distribution["WARNING"], error_ratio=round(errors / total, 4) if total else 0.0,
        severity_distribution=distribution, services=services,
        affected_services=[s.name for s in services if s.errors > 0],
        time_range=TimeRange(start=lo, end=hi, duration_seconds=span),
        incident_severity=severity, incident_severity_reasons=reasons,
    )
    return AnalysisResponse(
        engine_version=__version__, verdict=verdict, verdict_reason=reason, summary=summary, ingest=ingest,
        groups=groups, exception_patterns=patterns, timeline=buckets, bucket_seconds=bucket_seconds,
        spikes=spikes, cascade=cascade, correlations=correlations, hypotheses=hypotheses,
        recommended_steps=_steps(hypotheses, cascade, spikes, next((g.signature for g in groups if SEVERITY_RANK[g.severity] >= 3), None))
        if verdict == "incident_detected" else [],
        events=selected, events_total=total, events_truncated=truncated,
    )
