from app.analysis.correlation import detect_cascade, pairwise_correlations, service_onsets
from app.analysis.engine import assess_severity
from app.analysis.grouping import exception_patterns, group_events, signature
from app.analysis.hypotheses import evaluate, extract_status
from app.analysis.timeline import build_timeline, choose_bucket_seconds, detect_spikes
from app.models import Severity

from .helpers import ev, numbered


# ----------------------------------------------------------------------------- grouping


def test_signature_collapses_variable_parts_but_keeps_status_codes():
    a = signature("Timeout acquiring conn 10.0.0.5:5432 waiting=37 id=3f2a9c1d8e7b req 550e8400-e29b-41d4-a716-446655440000")
    b = signature("Timeout acquiring conn 10.0.0.9:5432 waiting=12 id=aa11bb22cc33 req 123e4567-e89b-12d3-a456-426614174000")
    assert a == b
    assert signature("upstream returned status=503") != signature("upstream returned status=500")
    assert signature("took 100ms") == signature("took 250ms")


def test_error_grouping_counts_and_order():
    events = numbered(
        [ev(0, i, "ERROR", "a", f"Timeout after {i}ms") for i in range(5)]
        + [ev(0, 10, "ERROR", "b", "Disk full")]
        + [ev(0, 11, "WARNING", "a", "slow request")]
        + [ev(0, 12, "INFO", "a", "fine")]
    )
    groups = group_events(events)
    assert [g.count for g in groups] == [5, 1, 1]
    assert groups[0].signature == "Timeout after <n>ms" and groups[0].services == ["a"]
    assert all(g.severity != Severity.INFO for g in groups)  # INFO never grouped


def test_exception_patterns_recurring_flag():
    events = numbered([ev(0, i * 30, "ERROR", "a", "java.lang.OutOfMemoryError: heap") for i in range(5)]
                      + [ev(0, 5, "ERROR", "a", "ValueError once")])
    buckets, size, idx = build_timeline(events)
    pats = {p.name: p for p in exception_patterns(events, idx)}
    assert pats["java.lang.OutOfMemoryError"].recurring
    assert not pats["ValueError"].recurring


# ----------------------------------------------------------------------------- timeline & spikes


def test_bucket_size_targets_about_sixty_buckets():
    assert choose_bucket_seconds(0) == 1
    assert choose_bucket_seconds(1200) == 30  # 1200/20+1 = 61 buckets would exceed 60
    assert choose_bucket_seconds(590) == 10
    assert choose_bucket_seconds(86400 * 365) >= 86400


def test_timeline_is_contiguous_and_counts_match():
    events = numbered([ev(0, 0, "INFO", "a", "x"), ev(0, 600, "ERROR", "a", "y"), ev(0, 1200, "WARNING", "a", "z")])
    buckets, size, idx = build_timeline(events)
    assert sum(b.total for b in buckets) == 3
    assert all(b2.start == b1.end for b1, b2 in zip(buckets, buckets[1:]))
    assert sum(b.counts["ERROR"] for b in buckets) == 1


def test_spike_detected_over_quiet_baseline():
    events = [ev(0, t, "INFO", "a", "ok") for t in range(0, 1200, 5)]
    events += [ev(0, t, "ERROR", "a", "boom") for t in range(600, 720, 2)]  # 60 errors in 2 minutes
    events += [ev(0, 100, "ERROR", "a", "stray")]
    numbered(events)
    buckets, size, idx = build_timeline(events)
    spikes = detect_spikes(events, buckets, idx)
    assert len(spikes) == 1 and spikes[0].total_errors >= 55
    assert spikes[0].services == ["a"]


def test_sustained_incident_longer_than_half_the_window_is_still_a_spike():
    events = [ev(0, t, "INFO", "a", "ok") for t in range(0, 1200, 5)]
    events += [ev(0, t, "ERROR", "a", "boom") for t in range(300, 1200)]
    numbered(events)
    buckets, _, idx = build_timeline(events)
    assert detect_spikes(events, buckets, idx)


def test_no_spike_for_flat_or_sparse_errors():
    events = [ev(0, t, "INFO", "a", "ok") for t in range(0, 1200, 5)]
    events += [ev(0, 100, "ERROR", "a", "x"), ev(0, 900, "ERROR", "a", "x")]
    numbered(events)
    buckets, _, idx = build_timeline(events)
    assert detect_spikes(events, buckets, idx) == []


def test_too_few_buckets_means_no_spike_claim():
    events = numbered([ev(0, t, "ERROR", "a", "x") for t in range(5)])
    buckets, _, idx = build_timeline(events)
    assert detect_spikes(events, buckets, idx) == []


# ----------------------------------------------------------------------------- cascade & correlation


def _chain(offsets: dict[str, float], n=6, step=3.0):
    out = []
    for svc, off in offsets.items():
        out += [ev(0, off + i * step, "ERROR", svc, f"{svc} failing") for i in range(n)]
    out += [ev(0, t, "INFO", "a", "ok") for t in range(0, 900, 10)]
    return numbered(out)


def test_cascade_detected_with_ordered_waves():
    events = _chain({"db": 200, "svc": 300, "api": 400, "web": 500})
    _, size, _ = build_timeline(events)
    c = detect_cascade(events, size, 900)
    assert c is not None
    assert c.origin_services == ["db"]
    assert [s.service for s in c.steps] == ["db", "svc", "api", "web"]
    assert [s.wave for s in c.steps] == [1, 2, 3, 4]


def test_simultaneous_failures_are_not_a_cascade():
    events = _chain({"a1": 300, "a2": 301, "a3": 302, "a4": 303})
    _, size, _ = build_timeline(events)
    assert detect_cascade(events, size, 900) is None


def test_two_services_are_not_a_cascade():
    events = _chain({"db": 200, "api": 400})
    _, size, _ = build_timeline(events)
    assert detect_cascade(events, size, 900) is None


def test_stray_early_error_does_not_become_the_cascade_origin():
    events = _chain({"x": 300, "y": 400, "z": 500})
    events.append(ev(0, 5, "ERROR", "z", "one stray error"))  # a single early error must not count as onset
    numbered(events)
    _, size, _ = build_timeline(events)
    onsets = service_onsets(events, size)
    assert onsets["z"][0].timestamp() > onsets["x"][0].timestamp()


def test_lagged_correlation_between_services():
    events = []
    for t in range(0, 900, 10):
        events.append(ev(0, t, "INFO", "a", "ok"))
    for t, n in ((200, 3), (230, 8), (260, 5), (290, 2), (500, 4), (530, 9), (560, 6)):
        events += [ev(0, t + i, "ERROR", "up", "fail") for i in range(n)]
        events += [ev(0, t + 30 + i, "ERROR", "down", "fail") for i in range(n)]
    numbered(events)
    buckets, size, idx = build_timeline(events)
    pairs = pairwise_correlations(events, len(buckets), idx, size)
    assert pairs and {pairs[0].service_a, pairs[0].service_b} == {"up", "down"}
    assert pairs[0].correlation > 0.9


# ----------------------------------------------------------------------------- severity rules


def test_incident_severity_rules():
    assert assess_severity(1000, 0, 0, [], None)[0] == "none"
    assert assess_severity(1000, 5, 0, [], None)[0] == "none"  # 0.5%: routine noise
    assert assess_severity(1000, 30, 0, [], None)[0] == "low"
    assert assess_severity(1000, 60, 0, [], None)[0] == "medium"
    assert assess_severity(1000, 200, 0, [], None)[0] == "high"
    assert assess_severity(1000, 400, 0, [], None)[0] == "critical"


# ----------------------------------------------------------------------------- hypotheses


def test_extract_status_variants():
    cases = {
        "upstream returned status=503": 503, "HTTP 502 bad": 502, "status code 504": 504,
        'GET /a/b 500 12ms': 500, '"status":429': 429, "504 Gateway Timeout from x": 504,
        "exit code 137": None, "waited 500 ms": None, "all fine": None,
    }
    for msg, want in cases.items():
        assert extract_status(msg) == want, msg


def _errs(n, msg, svc="a", sev="ERROR", start=0, step=2):
    return [ev(0, start + i * step, sev, svc, msg) for i in range(n)]


def test_pool_exhaustion_wins_over_generic_timeout():
    events = numbered(_errs(12, "TimeoutError: unable to acquire connection from pool (size=20) after 30000ms")
                      + _errs(5, "upstream returned status=500", svc="gw", start=3))
    hyps = evaluate(events, [], 17)
    assert hyps[0].category == "db_pool_exhaustion"
    assert "network_timeout" not in [h.category for h in hyps]  # pool timeouts are not double-counted
    assert any(h.category == "http_5xx" for h in hyps)


def test_each_cause_is_recognized():
    samples = {
        "memory_exhaustion": ("java.lang.OutOfMemoryError: Java heap space", "Container OOMKilled exit code 137"),
        "auth_failure": ("Authentication failed: invalid credentials", "JWT token expired, status=401"),
        "dependency_failure": ("connect ECONNREFUSED 10.0.0.1:5432", "upstream unavailable: service unavailable"),
        "rate_limiting": ("429 Too Many Requests, retry-after=30", "rate limit exceeded"),
        "network_timeout": ("read timeout after 5000ms", "context deadline exceeded"),
        "http_5xx": ("request failed status=500", "GET /x 502 20ms"),
        "db_pool_exhaustion": ("too many connections", "HikariPool-1 - Connection is not available, request timed out"),
    }
    for cat, (m1, m2) in samples.items():
        events = numbered(_errs(4, m1) + _errs(4, m2, start=1))
        hyps = evaluate(events, [], 8)
        assert cat in [h.category for h in hyps], (cat, [h.category for h in hyps])


def test_hypothesis_has_evidence_score_breakdown_and_actions():
    events = numbered(_errs(10, "java.lang.OutOfMemoryError: Java heap space") + _errs(3, "Memory pressure high: heap usage 90%", sev="WARNING", start=-30))
    h = evaluate(events, [], 10)[0]
    assert h.evidence and h.recommended_actions and h.affected_services[0].name == "a"
    assert abs(sum(c.points for c in h.score_breakdown) - h.evidence_score) < 0.11
    assert 0 <= h.evidence_score <= 100
    assert any(c.factor == "Early-warning precursors" and c.points == 10 for c in h.score_breakdown)


def test_scores_are_not_probabilities_and_spike_component_is_zero_without_spikes():
    events = numbered(_errs(10, "authentication failed"))
    h = evaluate(events, [], 10)[0]
    spike = next(c for c in h.score_breakdown if c.factor == "Coincides with error spike")
    assert spike.points == 0 and "no error spike" in spike.detail


def test_insufficient_evidence_thresholds():
    # two matching errors only: below MIN_MATCHES
    assert evaluate(numbered(_errs(2, "authentication failed")), [], 2) == []
    # three matches but only warnings: below MIN_ERROR_MATCHES
    assert evaluate(numbered(_errs(5, "authentication failed", sev="WARNING")), [], 0) == []


def test_info_events_never_support_hypotheses():
    assert evaluate(numbered(_errs(20, "authentication failed", sev="INFO")), [], 0) == []
