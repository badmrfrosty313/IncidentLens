"""Synthetic incident scenarios with documented, machine-checkable expected outcomes.

All data is fabricated and deterministic (seeded). Some messages deliberately contain fake
secrets (emails, passwords, tokens) so the redaction stage is exercised end to end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..models import ExpectedOutcome, LogFormat, ScenarioInfo
from .builder import LogBuilder


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    format: LogFormat
    extension: str
    expected: ExpectedOutcome
    render: Callable[[], str]

    def info(self) -> ScenarioInfo:
        return ScenarioInfo(id=self.id, name=self.name, description=self.description, format=self.format, expected=self.expected)


# ----------------------------------------------------------------------------- 1. DB pool


def _db_pool() -> str:
    b = LogBuilder(seed=101)
    b.traffic(["api-gateway", "orders-api", "billing-api"], 0, 1200, 0.35)
    b.add(5, "INFO", "orders-api", "Connected to postgres://orders_app:Tr0ub4dor-9x@db-primary.internal:5432/orders (pool size=20)")
    b.burst(40, 400, 6, "WARNING", "orders-api", lambda i, r: f"Slow query detected: SELECT * FROM orders WHERE status = 'open' took {r.randint(600, 1400)}ms")
    b.burst(430, 600, 9, "WARNING", "orders-api", lambda i, r: f"Connection pool utilization {80 + i}% (in_use={16 + i // 3}, size=20)")
    b.burst(600, 1000, 190, "ERROR", "orders-api", lambda i, r: f"TimeoutError: unable to acquire connection from pool (size=20, in_use=20, waiting={r.randint(8, 60)}) after 30000ms")
    b.burst(610, 900, 16, "CRITICAL", "orders-db-proxy", lambda i, r: "FATAL: remaining connection slots are reserved for non-replication superuser connections")
    b.burst(650, 1000, 130, "ERROR", "api-gateway", lambda i, r: f"upstream orders-api returned status=500 for GET /api/v1/orders/{r.randint(1000, 99999)}")
    b.add(1010, "WARNING", "orders-api", "Connection pool resized to 40 by operator")
    return b.to_plaintext("bracket")


# ----------------------------------------------------------------------------- 2. memory


def _memory() -> str:
    b = LogBuilder(seed=202)
    b.traffic(["image-processor", "thumbnail-worker", "scheduler"], 0, 1200, 0.3)
    b.burst(300, 700, 22, "WARNING", "image-processor", lambda i, r: f"Memory pressure high: heap usage {75 + min(i, 20)}% of 2048MB limit, GC pause {r.randint(800, 2600)}ms")
    b.burst(700, 1050, 40, "ERROR", "image-processor", lambda i, r: f"java.lang.OutOfMemoryError: Java heap space while resizing image batch {r.randint(100, 999)}")
    for t in (760, 850, 940, 1030):
        b.add(t, "CRITICAL", "image-processor", "Container killed: OOMKilled (exit code 137), restarting", exception="OOMKilled")
    b.burst(720, 1060, 24, "ERROR", "scheduler", lambda i, r: "Worker image-processor unreachable: connection refused")
    b.burst(740, 1000, 8, "WARNING", "thumbnail-worker", lambda i, r: "Queue depth growing, image-processor not consuming")
    return b.to_jsonl(mixed={"scheduler": "pino", "thumbnail-worker": "alias"})


# ----------------------------------------------------------------------------- 3. auth


def _auth() -> str:
    b = LogBuilder(seed=303)
    b.traffic(["auth-service", "profile-api", "checkout-api", "web-bff"], 0, 1200, 0.25)
    b.burst(430, 500, 5, "WARNING", "auth-service", lambda i, r: "Signing key rotation: key id kid-2025-03 not found in JWKS cache")
    b.burst(500, 900, 70, "ERROR", "auth-service", lambda i, r: r.choice([
        "JWT validation failed: signature verification failed (kid=kid-2025-03)",
        "Authentication failed: invalid credentials for user alice@example.com",
        "Authentication failed: token expired (jti=" + format(r.getrandbits(40), "x") + ")",
        "Login failed for user bob.smith@example.org: invalid credentials password=hunter2",
    ]))
    b.burst(505, 900, 90, "ERROR", "profile-api", lambda i, r: "Upstream auth check rejected request: status=401 Unauthorized (invalid token)")
    b.burst(508, 900, 80, "ERROR", "checkout-api", lambda i, r: "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.c2lnbmF0dXJl rejected, status=401")
    b.burst(509, 900, 35, "WARNING", "web-bff", lambda i, r: "401 from checkout-api, forcing user re-login")
    b.burst(520, 900, 25, "ERROR", "web-bff", lambda i, r: "Access denied: session expired, forbidden")
    return b.to_plaintext("dash")


# ----------------------------------------------------------------------------- 4. network timeout


def _network_timeout() -> str:
    b = LogBuilder(seed=404)
    b.traffic(["checkout-api", "payment-service", "notification-service"], 0, 1200, 0.35)
    b.burst(380, 1000, 60, "WARNING", "payment-service", lambda i, r: f"Retrying payment charge after timeout (attempt {r.randint(1, 3)}/3)")
    b.burst(420, 1000, 110, "ERROR", "payment-service", lambda i, r: r.choice([
        f"read timeout after 5000ms calling https://payments.partner.example/v2/charge (attempt {r.randint(1, 3)}/3)",
        "context deadline exceeded while calling payment provider",
        f"ETIMEDOUT connecting to 203.0.113.{r.randint(10, 40)}:443",
    ]))
    b.burst(440, 1000, 90, "ERROR", "checkout-api", lambda i, r: "504 Gateway Timeout from payment-service while confirming order")
    b.burst(900, 1000, 8, "ERROR", "payment-service", lambda i, r: "Circuit breaker open for payment-provider, failing fast")
    return b.to_plaintext("alt")


# ----------------------------------------------------------------------------- 5. cascade


def _cascade() -> str:
    b = LogBuilder(seed=505)
    chain = ["inventory-db", "inventory-service", "catalog-service", "search-api", "api-gateway", "web-frontend"]
    b.traffic(chain, 0, 1200, 0.25)
    b.burst(300, 420, 14, "ERROR", "inventory-db", lambda i, r: "Primary node unreachable: connection refused (replica set rs0)")
    b.burst(360, 700, 60, "ERROR", "inventory-service", lambda i, r: "Failed to connect to inventory-db: ECONNREFUSED 10.0.4.12:5432")
    b.burst(430, 800, 70, "ERROR", "catalog-service", lambda i, r: "Upstream inventory-service unavailable: service unavailable (503)")
    b.burst(500, 900, 70, "ERROR", "search-api", lambda i, r: r.choice([
        "Circuit breaker open for catalog-service", "Failed to call catalog-service: status=503"]))
    b.burst(570, 1000, 80, "ERROR", "api-gateway", lambda i, r: "upstream search-api error status=502 Bad Gateway")
    b.burst(640, 1050, 70, "ERROR", "web-frontend", lambda i, r: "API request failed with status 502 (GET /api/v1/search)")
    return b.to_jsonl()


# ----------------------------------------------------------------------------- 6. healthy


def _healthy() -> str:
    b = LogBuilder(seed=606)
    b.traffic(["api-gateway", "orders-api", "billing-api", "search-api"], 0, 1200, 0.3)
    warnings = [
        "Slow query detected: SELECT count(*) FROM audit_log took 850ms",
        "Deprecated endpoint /v1/users called by client=mobile-1.2",
        "Cache miss ratio 31% over last 5m",
        "Retrying request after timeout (attempt 1/3), succeeded on retry",
        "Connection pool utilization 68% (in_use=14, size=20)",
        "Rate limit headroom: 82% of partner quota used",
        "Memory usage 71% (soft threshold 80%)",
    ]
    for i in range(28):
        b.add(b.rng.uniform(10, 1190), "WARNING", b.rng.choice(["api-gateway", "orders-api", "billing-api", "search-api"]), warnings[i % len(warnings)])
    b.add(210, "ERROR", "billing-api", "Failed to send metrics batch to collector: connection reset by peer (will retry)")
    b.add(875, "ERROR", "search-api", "Scheduled index refresh exceeded 30s runtime")
    return b.to_plaintext("bracket")


# ----------------------------------------------------------------------------- 7. rate limiting


def _rate_limit() -> str:
    b = LogBuilder(seed=707)
    b.traffic(["api-gateway", "partner-sync", "billing-api"], 0, 1200, 0.3)
    b.burst(500, 900, 120, "ERROR", "partner-sync", lambda i, r: f"429 Too Many Requests from partner API; retry-after={r.choice([15, 30, 60])}s", status=429)
    b.burst(505, 900, 60, "WARNING", "api-gateway", lambda i, r: "Rate limit exceeded for client key, throttling requests")
    b.burst(520, 900, 50, "ERROR", "billing-api", lambda i, r: "Throttled by payment provider: rate limit exceeded")
    return b.to_json("alias")


def _exp(**kw) -> ExpectedOutcome:
    return ExpectedOutcome(**kw)


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "db-pool-exhaustion", "Database connection pool exhaustion",
        "orders-api runs out of database connections; the gateway then returns HTTP 500s.",
        "plaintext", "log",
        _exp(verdict="incident_detected", min_incident_severity="high", max_incident_severity="high",
             top_hypothesis="db_pool_exhaustion", required_hypotheses=["db_pool_exhaustion", "http_5xx"],
             forbidden_hypotheses=["memory_exhaustion", "auth_failure", "rate_limiting"],
             expect_spike=True, expect_cascade=False,
             required_affected_services=["orders-api", "api-gateway"],
             description="Pool-exhaustion errors in orders-api rank first; gateway 5xx is a lower-ranked symptom."),
        _db_pool,
    ),
    Scenario(
        "memory-exhaustion", "Memory exhaustion",
        "image-processor heap grows until OutOfMemoryError and repeated OOMKilled restarts.",
        "jsonl", "jsonl",
        _exp(verdict="incident_detected", min_incident_severity="high", top_hypothesis="memory_exhaustion",
             required_hypotheses=["memory_exhaustion"], forbidden_hypotheses=["auth_failure", "rate_limiting", "db_pool_exhaustion"],
             expect_spike=True, expect_cascade=False, required_affected_services=["image-processor", "scheduler"],
             description="OOM and heap evidence ranks first; scheduler 'connection refused' is a downstream effect. Mixed JSON key and level styles."),
        _memory,
    ),
    Scenario(
        "auth-service-failure", "Authentication service failure",
        "A signing-key rotation breaks JWT validation; downstream services return HTTP 401.",
        "plaintext", "log",
        _exp(verdict="incident_detected", min_incident_severity="medium", top_hypothesis="auth_failure",
             required_hypotheses=["auth_failure"], forbidden_hypotheses=["memory_exhaustion", "db_pool_exhaustion", "rate_limiting"],
             expect_spike=True, expect_cascade=False, required_affected_services=["auth-service", "profile-api", "checkout-api"],
             description="Authentication evidence ranks first. Contains fake emails, a password and a JWT that must be redacted."),
        _auth,
    ),
    Scenario(
        "network-dependency-timeout", "Network dependency timeout",
        "payment-service times out calling an external payment provider; checkout returns 504.",
        "plaintext", "log",
        _exp(verdict="incident_detected", min_incident_severity="medium", top_hypothesis="network_timeout",
             required_hypotheses=["network_timeout"], forbidden_hypotheses=["memory_exhaustion", "auth_failure", "db_pool_exhaustion", "rate_limiting"],
             expect_spike=True, expect_cascade=False, required_affected_services=["payment-service", "checkout-api"],
             description="Timeout, deadline and ETIMEDOUT evidence ranks first."),
        _network_timeout,
    ),
    Scenario(
        "cascading-microservice-failure", "Cascading microservice failure",
        "A database outage propagates through six services in successive waves.",
        "jsonl", "jsonl",
        _exp(verdict="incident_detected", min_incident_severity="critical", top_hypothesis="dependency_failure",
             required_hypotheses=["dependency_failure"], forbidden_hypotheses=["memory_exhaustion", "auth_failure", "rate_limiting"],
             expect_spike=True, expect_cascade=True,
             required_affected_services=["inventory-db", "inventory-service", "catalog-service", "search-api", "api-gateway", "web-frontend"],
             description="Cascade detected with inventory-db as origin; dependency failure ranks first."),
        _cascade,
    ),
    Scenario(
        "healthy-system", "Healthy system with routine warnings",
        "Normal traffic with routine warnings and two isolated, self-healing errors. Must NOT raise an incident.",
        "plaintext", "log",
        _exp(verdict="no_incident", min_incident_severity="none", max_incident_severity="none",
             forbidden_hypotheses=["db_pool_exhaustion", "network_timeout", "memory_exhaustion", "auth_failure", "dependency_failure", "rate_limiting", "http_5xx"],
             expect_spike=False, expect_cascade=False,
             description="False-positive guard: warning text mentions pools, timeouts, memory and rate limits but must not produce hypotheses."),
        _healthy,
    ),
    Scenario(
        "rate-limit-storm", "Rate limiting storm",
        "A partner API throttles partner-sync with HTTP 429, which spills into billing.",
        "json", "json",
        _exp(verdict="incident_detected", min_incident_severity="medium", top_hypothesis="rate_limiting",
             required_hypotheses=["rate_limiting"], forbidden_hypotheses=["memory_exhaustion", "auth_failure", "db_pool_exhaustion"],
             expect_spike=True, expect_cascade=False, required_affected_services=["partner-sync", "billing-api"],
             description="429 / retry-after evidence ranks first."),
        _rate_limit,
    ),
)

_BY_ID = {s.id: s for s in SCENARIOS}


def get_scenario(scenario_id: str) -> Scenario | None:
    return _BY_ID.get(scenario_id)
