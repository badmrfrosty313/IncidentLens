"""Large synthetic log generator for the benchmark (deterministic, no I/O)."""

from __future__ import annotations

from .builder import LogBuilder

_SERVICES = ["api-gateway", "orders-api", "billing-api", "auth-service", "search-api", "inventory-service", "web-bff", "worker"]
_ERRORS = [
    "TimeoutError: unable to acquire connection from pool (size=20, in_use=20, waiting={n})",
    "upstream inventory-service returned status=503",
    "read timeout after {n}ms calling https://partner.example/api",
    "Authentication failed for user user{n}@example.com: invalid credentials",
    "java.lang.OutOfMemoryError: Java heap space",
]
_WARNINGS = ["Slow query took {n}ms", "Cache miss ratio {n}%", "Retrying request (attempt {a}/3)", "Connection pool utilization {n}%"]


def generate_plaintext(n_events: int, seed: int = 7) -> str:
    """~n_events lines: mostly INFO, background WARN/ERROR, plus an error burst mid-window.

    Every 50th line carries a fake secret so the redaction stage does real work.
    """
    b = LogBuilder(seed=seed)
    r = b.rng
    span = max(60.0, n_events * 0.05)
    burst_lo, burst_hi = span * 0.45, span * 0.55
    for i in range(n_events):
        in_burst = i % 10 < 6 and i > n_events * 0.45 and i < n_events * 0.55
        t = burst_lo + (burst_hi - burst_lo) * r.random() if in_burst else r.uniform(0, span)
        svc = r.choice(_SERVICES)
        x = r.random()
        if in_burst or x > 0.93:
            msg = r.choice(_ERRORS).format(n=r.randint(1, 5000))
            level = "ERROR" if x < 0.99 else "CRITICAL"
        elif x > 0.83:
            level, msg = "WARNING", r.choice(_WARNINGS).format(n=r.randint(1, 99), a=r.randint(1, 3))
        else:
            level = "INFO"
            msg = f"GET /api/v1/items/{r.randint(1, 99999)} 200 {r.randint(3, 200)}ms request_id={r.getrandbits(32):08x}"
        if i % 50 == 0:
            msg += " api_key=sk-test-0123456789abcdefABCDEF contact=ops@example.com"
        b.add(t, level, svc, msg)
    return b.to_plaintext("bracket")
