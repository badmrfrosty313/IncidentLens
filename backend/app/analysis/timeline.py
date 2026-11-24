"""Timeline bucketing and error-spike detection."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import median

from ..models import SEVERITY_RANK, LogEvent, Severity, Spike, TimelineBucket

TARGET_BUCKETS = 60
_CANDIDATE_SECONDS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400)
MIN_BUCKETS_FOR_SPIKES = 8
MIN_SPIKE_COUNT = 5  # a spike bucket needs at least this many ERROR+CRITICAL events
SPIKE_SIGMA = 3.0

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def is_error(e: LogEvent) -> bool:
    return SEVERITY_RANK[e.severity] >= SEVERITY_RANK[Severity.ERROR]


def choose_bucket_seconds(span_seconds: float) -> int:
    for size in _CANDIDATE_SECONDS:
        if span_seconds / size + 1 <= TARGET_BUCKETS:
            return size
    return int(math.ceil(span_seconds / TARGET_BUCKETS / 86400) * 86400)


def build_timeline(events: list[LogEvent]) -> tuple[list[TimelineBucket], int, dict[int, int]]:
    """Return (contiguous buckets, bucket size in seconds, event id -> bucket index)."""
    stamped = [e for e in events if e.timestamp is not None]
    if not stamped:
        return [], 1, {}
    lo = min(e.timestamp for e in stamped)  # type: ignore[type-var]
    hi = max(e.timestamp for e in stamped)  # type: ignore[type-var]
    size = choose_bucket_seconds((hi - lo).total_seconds())
    origin = math.floor((lo - _EPOCH).total_seconds() / size) * size
    n_buckets = int((hi - _EPOCH).total_seconds() // size - origin // size) + 1
    keys = [s.value for s in Severity]
    counts = [dict.fromkeys(keys, 0) for _ in range(n_buckets)]
    index: dict[int, int] = {}
    for e in stamped:
        i = int(((e.timestamp - _EPOCH).total_seconds() - origin) // size)  # type: ignore[operator]
        counts[i][e.severity.value] += 1
        index[e.id] = i
    buckets = []
    for i, c in enumerate(counts):
        start = _EPOCH + timedelta(seconds=origin + i * size)
        buckets.append(TimelineBucket(start=start, end=start + timedelta(seconds=size), counts=c, total=sum(c.values())))
    return buckets, size, index


def error_series(buckets: list[TimelineBucket]) -> list[int]:
    return [b.counts["ERROR"] + b.counts["CRITICAL"] for b in buckets]


def detect_spikes(
    events: list[LogEvent], buckets: list[TimelineBucket], index: dict[int, int]
) -> list[Spike]:
    """Flag runs of buckets whose ERROR+CRITICAL count is far above a quiet baseline.

    Baseline = median of the quietest half of buckets (robust to long incidents).
    Threshold = max(baseline + 3 * max(sqrt(baseline), 1), MIN_SPIKE_COUNT).
    """
    if len(buckets) < MIN_BUCKETS_FOR_SPIKES:
        return []
    series = error_series(buckets)
    quiet = sorted(series)[: max(1, len(series) // 2)]
    baseline = float(median(quiet))
    threshold = max(baseline + SPIKE_SIGMA * max(math.sqrt(baseline), 1.0), float(MIN_SPIKE_COUNT))
    hot = [i for i, c in enumerate(series) if c >= threshold]
    if not hot:
        return []
    runs: list[list[int]] = [[hot[0]]]
    for i in hot[1:]:
        if i - runs[-1][-1] <= 2:  # tolerate a single quiet bucket inside one incident
            runs[-1].append(i)
        else:
            runs.append([i])
    by_bucket: dict[int, list[LogEvent]] = {}
    for e in events:
        if is_error(e) and e.id in index:
            by_bucket.setdefault(index[e.id], []).append(e)
    spikes = []
    for run in runs:
        lo, hi = run[0], run[-1]
        in_run = [e for i in range(lo, hi + 1) for e in by_bucket.get(i, [])]
        svc: dict[str, int] = {}
        for e in in_run:
            svc[e.service] = svc.get(e.service, 0) + 1
        spikes.append(
            Spike(
                start=buckets[lo].start, end=buckets[hi].end,
                peak_count=max(series[lo : hi + 1]), total_errors=len(in_run),
                baseline=round(baseline, 2), threshold=round(threshold, 2),
                services=[s for s, _ in sorted(svc.items(), key=lambda kv: (-kv[1], kv[0]))][:6],
            )
        )
    return spikes
