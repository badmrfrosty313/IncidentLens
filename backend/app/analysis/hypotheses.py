"""Rule-based root-cause hypothesis generation with a transparent heuristic evidence score.

Each rule is a set of named regex indicators (plus optional HTTP status indicators). An event
can support several hypotheses. The score is a sum of documented components (max 100) and is
a ranking aid, NOT a probability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .grouping import signature
from ..models import (
    SEVERITY_RANK, AffectedService, EvidenceItem, Hypothesis, IndicatorHit, LogEvent,
    ScoreComponent, Severity, Spike,
)

MIN_MATCHES = 3
MIN_ERROR_MATCHES = 2
MIN_SCORE = 25.0

_WARN = SEVERITY_RANK[Severity.WARNING]
_ERR = SEVERITY_RANK[Severity.ERROR]

_STATUS_KEYWORD = re.compile(
    r"(?:\bstatus(?:[_\s]?code)?|\bhttp(?:/\d(?:\.\d)?)?|\bresponded\s+with|\breturned|\bresponse)"
    r"\s*[=:\"']*\s*(?P<s>[45]\d\d)\b",
    re.IGNORECASE,
)
_STATUS_ACCESS = re.compile(
    r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+\S+\s+(?:HTTP/\d(?:\.\d)?\s+)?(?P<s>[45]\d\d)\b"
)
_STATUS_LEADING = re.compile(r"^\s*(?P<s>[45]\d\d)\s+[A-Z]")  # "504 Gateway Timeout ..."


def extract_status(message: str) -> int | None:
    head = message[:600]
    for rx in (_STATUS_KEYWORD, _STATUS_ACCESS, _STATUS_LEADING):
        m = rx.search(head)
        if m:
            return int(m.group("s"))
    return None


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


@dataclass(frozen=True)
class Indicator:
    name: str
    label: str
    pattern: re.Pattern[str] | None = None
    statuses: frozenset[int] = frozenset()
    status_range: tuple[int, int] | None = None  # inclusive


@dataclass(frozen=True)
class Rule:
    category: str
    title: str
    blurb: str
    indicators: tuple[Indicator, ...]
    actions: tuple[str, ...]
    excludes: tuple[str, ...] = ()


RULES: tuple[Rule, ...] = (
    Rule(
        "db_pool_exhaustion", "Database connection pool exhaustion",
        "connection-pool exhaustion or connection-limit errors",
        (
            Indicator("pool_exhausted", "Pool exhausted / full / timed out",
                      _rx(r"pool[^\n]{0,40}(?:exhaust|\bfull\b|saturat|deplet|timed?\s*out|limit\s+(?:reached|exceeded))")),
            Indicator("cannot_acquire_connection", "Cannot acquire a connection",
                      _rx(r"(?:unable|failed|cannot|could\s*not|timeout)[^\n]{0,30}(?:acquire|obtain|checkout|check\s*out|get)[^\n]{0,30}connection")),
            Indicator("too_many_connections", "Too many connections / slots exhausted",
                      _rx(r"too\s+many\s+(?:db\s+|database\s+|client\s+)?connections|remaining\s+connection\s+slots|max_connections|connection\s+limit")),
            Indicator("pool_library_error", "Pool library timeout (Hikari / QueuePool)",
                      _rx(r"hikaripool|queuepool\s+limit|connection\s+is\s+not\s+available|timeout\s+waiting\s+for\s+(?:a\s+)?connection")),
        ),
        (
            "Compare pool size, in-use and waiting counts over the incident window for the affected service.",
            "Check database-side active connection count and max_connections; look for connection leaks (unreleased connections, long transactions).",
            "Identify slow or blocked queries during the window (slow query log, pg_stat_activity / SHOW PROCESSLIST).",
            "Review recent deploys or config changes to pool size, timeouts, or traffic volume.",
            "As a mitigation to evaluate, temporarily raise the pool limit or shed load while the root cause is confirmed.",
        ),
    ),
    Rule(
        "network_timeout", "Network or dependency timeouts",
        "timeout, deadline-exceeded or socket-level network errors",
        (
            Indicator("timeout", "Timeout messages", _rx(r"time[sd]?[\s-]?out|timeout")),
            Indicator("deadline_exceeded", "Deadline exceeded", _rx(r"deadline\s+exceeded|context\s+deadline")),
            Indicator("socket_errors", "Socket / reset errors",
                      _rx(r"etimedout|econnreset|connection\s+reset|broken\s+pipe|socket\s+hang\s*up|i/o\s+timeout")),
            Indicator("http_timeout_status", "HTTP 504 / 408 responses", statuses=frozenset({504, 408})),
        ),
        (
            "Identify which remote endpoint the timeouts target and check its own latency and error dashboards.",
            "Check network path health: DNS, load balancer, security groups / firewall, packet loss between the two hosts.",
            "Compare configured client timeouts and retry policy against the dependency's observed latency.",
            "Look for retry amplification: retries can multiply load on an already slow dependency.",
        ),
        excludes=("db_pool_exhaustion",),
    ),
    Rule(
        "memory_exhaustion", "Memory exhaustion",
        "out-of-memory, heap exhaustion or OOM-kill events",
        (
            Indicator("oom", "Out-of-memory errors",
                      _rx(r"out\s*of\s*memory|outofmemory|\boom\b|oom[-_ ]?kill|memoryerror|cannot\s+allocate\s+memory|\benomem\b")),
            Indicator("heap", "Heap / GC exhaustion",
                      _rx(r"java\s+heap\s+space|heap\s+(?:space|exhaust|limit)|gc\s+overhead|allocation\s+failure|javascript\s+heap")),
            Indicator("memory_limit", "Memory limit exceeded / container killed",
                      _rx(r"memory\s+(?:limit|quota|usage|pressure)[^\n]{0,30}(?:exceed|exhaust|critical|high)|exceeded\s+memory|killed\s+process[^\n]{0,60}memory|container\s+killed|exit\s*code\s*137")),
        ),
        (
            "Plot memory usage / heap and GC metrics for the affected service across the incident window.",
            "Check for container restarts / OOMKilled events and compare against configured memory limits.",
            "Capture a heap dump or profile (or review one if auto-captured) to find what is growing.",
            "Correlate onset with deploys, traffic changes, or large payloads / batch jobs.",
        ),
    ),
    Rule(
        "auth_failure", "Authentication or authorization failures",
        "authentication, credential, token or authorization failures",
        (
            Indicator("auth_failed", "Authentication failed",
                      _rx(r"authenticat(?:ion|e)[^\n]{0,20}(?:fail|error|denied|reject|refused)|login\s+failed|failed\s+(?:login|authentication)")),
            Indicator("invalid_credentials", "Invalid credentials / token",
                      _rx(r"invalid\s+(?:credentials?|token|api[\s_-]?key|password|signature|jwt)|bad\s+credentials|wrong\s+password|credentials?\s+(?:rejected|invalid|expired)")),
            Indicator("token_expired", "Token expired / revoked",
                      _rx(r"(?:token|jwt|session|certificate|credentials?)[^\n]{0,20}(?:expired|revoked)|expired\s+(?:token|jwt|session|credentials?)|signature\s+verification\s+failed|invalid_grant")),
            Indicator("unauthorized", "Unauthorized / forbidden",
                      _rx(r"\bunauthori[sz]ed\b|access\s+denied|permission\s+denied|\bforbidden\b")),
            Indicator("http_401_403", "HTTP 401 / 403 responses", statuses=frozenset({401, 403})),
        ),
        (
            "Check the identity provider / auth service health and recent changes (key rotation, certificate or secret expiry).",
            "Verify clock skew between services (token validity windows) and JWKS / signing-key propagation.",
            "Separate a credential problem for one client from a platform-wide failure by grouping failures per caller.",
            "Review recent deploys and config changes affecting token issuance, scopes or audience claims.",
        ),
    ),
    Rule(
        "dependency_failure", "Downstream dependency failure",
        "refused connections, unavailable upstreams or open circuit breakers",
        (
            Indicator("connection_refused", "Connection refused / unreachable",
                      _rx(r"connection\s+refused|econnrefused|no\s+route\s+to\s+host|host\s+unreachable")),
            Indicator("service_unavailable", "Service / upstream unavailable",
                      _rx(r"service\s+unavailable|upstream[^\n]{0,30}(?:unavailable|unhealthy|error|failed|down)|no\s+healthy\s+upstream|bad\s+gateway|backend[^\n]{0,20}(?:down|unavailable)")),
            Indicator("dns_failure", "DNS / name resolution failure",
                      _rx(r"name\s+resolution|enotfound|getaddrinfo|dns[^\n]{0,20}(?:fail|error)|unknown\s+host|could\s+not\s+resolve")),
            Indicator("breaker_or_call_failure", "Circuit breaker open / call failures",
                      _rx(r"circuit[\s-]?breaker[^\n]{0,20}(?:open|trip)|failed\s+to\s+(?:call|reach|connect\s+to)|dependency[^\n]{0,30}(?:fail|unavailable|down|error)|health\s*check[^\n]{0,20}fail")),
            Indicator("http_502_503", "HTTP 502 / 503 responses", statuses=frozenset({502, 503})),
        ),
        (
            "Identify the dependency named in the errors and check its health, deployment status and capacity.",
            "Use the cascade onset order (if shown) to find which service failed first and start there.",
            "Check whether circuit breakers, retries and timeouts are configured to contain a failing dependency.",
            "Verify network reachability and service discovery / DNS for the failing dependency.",
        ),
        excludes=("db_pool_exhaustion",),
    ),
    Rule(
        "rate_limiting", "Rate limiting or throttling",
        "rate-limit, throttling or quota errors",
        (
            Indicator("rate_limit", "Rate limit / throttle messages",
                      _rx(r"rate[\s-]?limit(?:ed|ing|s)?|rate\s+exceeded|ratelimitexceeded|too\s+many\s+requests|throttl(?:ed|ing)|quota\s+(?:exceeded|exhausted)|request\s+limit")),
            Indicator("retry_after", "Retry-After hints", _rx(r"retry[-\s_]?after")),
            Indicator("http_429", "HTTP 429 responses", statuses=frozenset({429})),
        ),
        (
            "Identify which client or API key is being limited and which limit (per-key, per-IP, global) was hit.",
            "Compare request rate against configured quotas; look for a client retry storm or a traffic spike.",
            "Check whether the limiter is yours or a third party's, and review backoff / jitter in callers.",
            "Evaluate raising the quota or adding client-side backoff and request coalescing.",
        ),
    ),
    Rule(
        "http_5xx", "Elevated HTTP 5xx errors (symptom)",
        "HTTP 5xx server errors",
        (
            Indicator("http_5xx_status", "HTTP 5xx responses", status_range=(500, 599)),
            Indicator("internal_error_text", "Internal server error text", _rx(r"internal\s+server\s+error")),
        ),
        (
            "Treat 5xx as a symptom: find the first service emitting 5xx and inspect its own errors for the underlying cause.",
            "Break 5xx down by endpoint and status code to see whether one route or all routes are affected.",
            "Compare against other hypotheses; a specific cause with a higher score usually explains the 5xx.",
        ),
    ),
)

def _indicator_hits(ind: Indicator, message: str, status: int | None) -> bool:
    if ind.pattern is not None and ind.pattern.search(message):
        return True
    if status is not None:
        if status in ind.statuses:
            return True
        if ind.status_range and ind.status_range[0] <= status <= ind.status_range[1]:
            return True
    return False


@dataclass
class _Match:
    event: LogEvent
    indicators: list[str]


def evaluate(
    events: list[LogEvent],
    spikes: list[Spike],
    total_error_events: int,
) -> list[Hypothesis]:
    """Return ranked hypotheses (possibly empty). Only WARNING+ events are considered."""
    matches: dict[str, list[_Match]] = {r.category: [] for r in RULES}
    for e in events:
        if SEVERITY_RANK[e.severity] < _WARN:
            continue
        status = extract_status(e.message)
        hit_cats: set[str] = set()
        for rule in RULES:
            if any(x in hit_cats for x in rule.excludes):
                continue
            names = [i.name for i in rule.indicators if _indicator_hits(i, e.message, status)]
            if names:
                matches[rule.category].append(_Match(e, names))
                hit_cats.add(rule.category)

    hypotheses: list[Hypothesis] = []
    for rule in RULES:
        ms = matches[rule.category]
        n_err = sum(1 for m in ms if SEVERITY_RANK[m.event.severity] >= _ERR)
        if len(ms) < MIN_MATCHES or n_err < MIN_ERROR_MATCHES:
            continue
        hyp = _score(rule, ms, n_err, spikes, total_error_events)
        if hyp.evidence_score >= MIN_SCORE:
            hypotheses.append(hyp)
    hypotheses.sort(key=lambda h: (-h.evidence_score, -h.matched_events, h.category))
    for i, h in enumerate(hypotheses, start=1):
        h.rank = i
    return hypotheses


def _in_spike(m: _Match, spikes: list[Spike]) -> bool:
    ts = m.event.timestamp
    return ts is not None and any(s.start <= ts < s.end for s in spikes)


def _score(rule: Rule, ms: list[_Match], n_err: int, spikes: list[Spike], total_errors: int) -> Hypothesis:
    n = len(ms)
    ind_counts: dict[str, int] = {}
    for m in ms:
        for name in m.indicators:
            ind_counts[name] = ind_counts.get(name, 0) + 1
    labels = {i.name: i.label for i in rule.indicators}
    distinct = len(ind_counts)
    in_spike = sum(1 for m in ms if _in_spike(m, spikes)) if spikes else 0
    err_ts = [m.event.timestamp for m in ms if SEVERITY_RANK[m.event.severity] >= _ERR and m.event.timestamp]
    first_err = min(err_ts) if err_ts else None
    precursors = sum(
        1 for m in ms
        if SEVERITY_RANK[m.event.severity] == _WARN and first_err and m.event.timestamp and m.event.timestamp < first_err
    )

    comps = [
        ScoreComponent(factor="Matching volume", max_points=25.0, points=round(min(1.0, n / 10) * 25, 1),
                       detail=f"{n} matching event(s); full points at 10 or more"),
        ScoreComponent(factor="Indicator diversity", max_points=15.0, points=round(min(2, distinct) / 2 * 15, 1),
                       detail=f"{distinct} distinct indicator(s) matched; full points at 2 or more"),
        ScoreComponent(factor="Severity", max_points=15.0, points=round(n_err / n * 15, 1),
                       detail=f"{n_err} of {n} matching events are ERROR or CRITICAL"),
        ScoreComponent(
            factor="Coincides with error spike", max_points=20.0,
            points=round(in_spike / n * 20, 1) if spikes else 0.0,
            detail=(f"{in_spike} of {n} matching events fall inside a detected error spike" if spikes
                    else "no error spike was detected, so no points are awarded"),
        ),
        ScoreComponent(factor="Share of all errors", max_points=15.0,
                       points=round(min(1.0, n_err / total_errors) * 15, 1) if total_errors else 0.0,
                       detail=f"{n_err} of {total_errors} ERROR/CRITICAL events in the input match"),
        ScoreComponent(factor="Early-warning precursors", max_points=10.0, points=10.0 if precursors else 0.0,
                       detail=(f"{precursors} matching WARNING event(s) precede the first matching error"
                               if precursors else "no matching warnings precede the first matching error")),
    ]
    score = round(min(100.0, sum(c.points for c in comps)), 1)
    level = "strong" if score >= 65 else "moderate" if score >= 45 else "weak"

    svc: dict[str, int] = {}
    for m in ms:
        svc[m.event.service] = svc.get(m.event.service, 0) + 1
    affected = [AffectedService(name=s, matched_events=c) for s, c in sorted(svc.items(), key=lambda kv: (-kv[1], kv[0]))]
    stamps = [m.event.timestamp for m in ms if m.event.timestamp]

    # Evidence: earliest example per distinct message signature, in time order, max 6.
    seen: set[str] = set()
    evidence: list[EvidenceItem] = []
    for m in ms:
        sig = signature(m.event.message)
        if sig in seen:
            continue
        seen.add(sig)
        evidence.append(
            EvidenceItem(
                event_id=m.event.id, timestamp=m.event.timestamp, service=m.event.service,
                severity=m.event.severity, message=m.event.message.split("\n", 1)[0][:300],
                indicator=labels[m.indicators[0]],
            )
        )
        if len(evidence) == 6:
            break

    first, last = (min(stamps), max(stamps)) if stamps else (None, None)
    summary = (
        f"{n} event(s) across {len(affected)} service(s) matched {rule.blurb}"
        + (f", first at {first:%Y-%m-%d %H:%M:%S}Z and last at {last:%H:%M:%S}Z" if first and last else "")
        + f". Matched indicators: {', '.join(labels[k] for k in ind_counts)}."
    )
    return Hypothesis(
        rank=0, category=rule.category, title=rule.title, evidence_score=score, evidence_level=level,  # type: ignore[arg-type]
        summary=summary, matched_events=n, first_seen=first, last_seen=last,
        affected_services=affected[:8],
        indicators=[IndicatorHit(name=k, label=labels[k], count=v) for k, v in sorted(ind_counts.items(), key=lambda kv: -kv[1])],
        evidence=evidence, score_breakdown=comps, recommended_actions=list(rule.actions),
    )
