"""Temporal correlation between services and cascading-failure detection."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import StatisticsError, correlation

from ..models import CascadeFinding, CascadeStep, CorrelationPair, LogEvent
from .timeline import error_series, is_error

MIN_SERVICE_ERRORS = 3
MIN_CASCADE_WAVES = 3
MAX_LAG_BUCKETS = 3
MIN_CORRELATION = 0.6


def service_onsets(events: list[LogEvent], bucket_seconds: int) -> dict[str, tuple[datetime, int]]:
    """Per-service error onset: first error that starts a burst of >=3 errors within a short window.

    Using a burst start (not the first ever error) keeps a stray early error from
    making a service look like the origin of an incident.
    """
    window = max(60.0, 5.0 * bucket_seconds)
    per: dict[str, list[datetime]] = {}
    for e in events:
        if is_error(e) and e.timestamp is not None:
            per.setdefault(e.service, []).append(e.timestamp)
    onsets: dict[str, tuple[datetime, int]] = {}
    for svc, stamps in per.items():
        if len(stamps) < MIN_SERVICE_ERRORS:
            continue
        stamps.sort()
        for i in range(len(stamps) - MIN_SERVICE_ERRORS + 1):
            if (stamps[i + MIN_SERVICE_ERRORS - 1] - stamps[i]).total_seconds() <= window:
                onsets[svc] = (stamps[i], len(stamps))
                break
    return onsets


def detect_cascade(
    events: list[LogEvent], bucket_seconds: int, span_seconds: float
) -> CascadeFinding | None:
    """A cascade = error onsets arriving in >=3 distinct, ordered waves with bounded gaps."""
    onsets = service_onsets(events, bucket_seconds)
    if len(onsets) < MIN_CASCADE_WAVES:
        return None
    stagger = max(float(bucket_seconds), 5.0)
    max_gap = max(120.0, 0.25 * span_seconds)
    ordered = sorted(onsets.items(), key=lambda kv: (kv[1][0], kv[0]))
    waves: list[list[tuple[str, datetime, int]]] = []
    for svc, (onset, count) in ordered:
        if waves and (onset - waves[-1][0][1]).total_seconds() < stagger:
            waves[-1].append((svc, onset, count))
        else:
            waves.append([(svc, onset, count)])
    if len(waves) < MIN_CASCADE_WAVES:
        return None
    for prev, nxt in zip(waves, waves[1:]):
        if (nxt[0][1] - prev[-1][1]).total_seconds() > max_gap:
            return None
    t0 = waves[0][0][1]
    steps = [
        CascadeStep(service=svc, onset=onset, offset_seconds=(onset - t0).total_seconds(), error_count=count, wave=w + 1)
        for w, wave in enumerate(waves)
        for svc, onset, count in wave
    ]
    span = (steps[-1].onset - t0).total_seconds()
    origin = [s for s, _, _ in waves[0]]
    return CascadeFinding(
        origin_services=origin,
        steps=steps,
        span_seconds=span,
        note=(
            f"Error onsets reached {len(steps)} services in {len(waves)} successive waves over {span:.0f}s, "
            f"starting at {', '.join(origin)}. Onset order shows where failures appeared first; "
            "it is a lead for investigation, not proof of causality."
        ),
    )


def _lagged_r(a: list[int], b: list[int], lag: int) -> float | None:
    """Pearson r between a[i] and b[i+lag]. None when undefined or too few points."""
    if lag >= 0:
        xs, ys = a[: len(a) - lag], b[lag:]
    else:
        xs, ys = a[-lag:], b[: len(b) + lag]
    if len(xs) < 8 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    try:
        return correlation(xs, ys)
    except StatisticsError:
        return None


def pairwise_correlations(
    events: list[LogEvent], n_buckets: int, index: dict[int, int], bucket_seconds: int, top_services: int = 8
) -> list[CorrelationPair]:
    """Correlate per-service error-count series (zero lag and +-3 buckets)."""
    if n_buckets < 8:
        return []
    # Count first, select the top services, and only then allocate per-bucket arrays. Allocating
    # for every service up front costs O(services x buckets) and is attacker-controlled.
    totals = Counter(e.service for e in events if is_error(e) and e.id in index)
    services = [s for s, n in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])) if n >= MIN_SERVICE_ERRORS][:top_services]
    wanted = set(services)
    series: dict[str, list[int]] = {s: [0] * n_buckets for s in services}
    for e in events:
        if e.service in wanted and is_error(e) and e.id in index:
            series[e.service][index[e.id]] += 1
    pairs: list[CorrelationPair] = []
    for i, sa in enumerate(services):
        for sb in services[i + 1 :]:
            best: tuple[float, int] | None = None
            for lag in range(-MAX_LAG_BUCKETS, MAX_LAG_BUCKETS + 1):
                r = _lagged_r(series[sa], series[sb], lag)
                if r is not None and (best is None or r > best[0] + 1e-9 or (abs(r - best[0]) <= 1e-9 and abs(lag) < abs(best[1]))):
                    best = (r, lag)
            if best is None or best[0] < MIN_CORRELATION:
                continue
            r, lag = best
            secs = float(lag * bucket_seconds)
            if lag == 0:
                text = f"{sa} and {sb} error counts move together"
            elif lag > 0:
                text = f"{sb} errors trail {sa} errors by about {abs(secs):.0f}s"
            else:
                text = f"{sa} errors trail {sb} errors by about {abs(secs):.0f}s"
            pairs.append(CorrelationPair(service_a=sa, service_b=sb, correlation=round(r, 3), lag_seconds=secs, interpretation=text))
    pairs.sort(key=lambda p: (-p.correlation, p.service_a, p.service_b))
    return pairs[:10]


__all__ = ["service_onsets", "detect_cascade", "pairwise_correlations", "error_series"]
