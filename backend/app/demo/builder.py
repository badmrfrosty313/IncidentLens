"""Deterministic synthetic log builder used by demo scenarios and the benchmark."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

START = datetime(2025, 3, 14, 9, 0, 0, tzinfo=timezone.utc)

_ENDPOINTS = ["/api/v1/orders", "/api/v1/orders/{id}", "/api/v1/users/me", "/api/v1/catalog", "/api/v1/cart", "/healthz", "/api/v1/search"]
_METHODS = ["GET", "GET", "GET", "POST", "PUT"]


@dataclass
class Row:
    ts: datetime
    level: str  # INFO / WARNING / ERROR / CRITICAL
    service: str
    message: str
    extra: dict = field(default_factory=dict)


class LogBuilder:
    def __init__(self, seed: int, start: datetime = START) -> None:
        self.rng = random.Random(seed)
        self.start = start
        self.rows: list[Row] = []

    def add(self, offset: float, level: str, service: str, message: str, **extra: object) -> None:
        self.rows.append(Row(self.start + timedelta(seconds=offset), level, service, message, dict(extra)))

    def traffic(self, services: list[str], t0: float, t1: float, rate: float) -> None:
        """Healthy INFO request logs: ``rate`` events/second per service over [t0, t1)."""
        r = self.rng
        for svc in services:
            for _ in range(int((t1 - t0) * rate)):
                path = r.choice(_ENDPOINTS).replace("{id}", str(r.randint(1000, 99999)))
                self.add(r.uniform(t0, t1), "INFO", svc,
                         f"{r.choice(_METHODS)} {path} 200 {r.randint(4, 140)}ms request_id={r.getrandbits(32):08x}")

    def burst(self, t0: float, t1: float, n: int, level: str, service: str, make, **extra: object) -> None:
        """``n`` events spread uniformly over [t0, t1); ``make(i, rng)`` returns the message."""
        for i in range(n):
            self.add(self.rng.uniform(t0, t1), level, service, make(i, self.rng), **extra)

    def sorted_rows(self) -> list[Row]:
        return sorted(self.rows, key=lambda r: (r.ts, r.service, r.message))

    # -- renderers ---------------------------------------------------------------------

    def to_plaintext(self, style: str = "bracket") -> str:
        lines = []
        for r in self.sorted_rows():
            iso = r.ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{r.ts.microsecond // 1000:03d}Z"
            if style == "bracket":  # 2025-03-14T09:00:00.000Z INFO  [svc] message
                lines.append(f"{iso} {r.level:<8} [{r.service}] {r.message}")
            elif style == "dash":  # 2025-03-14 09:00:00,000 ERROR svc - message
                stamp = r.ts.strftime("%Y-%m-%d %H:%M:%S,") + f"{r.ts.microsecond // 1000:03d}"
                lines.append(f"{stamp} {r.level} {r.service} - {r.message}")
            else:  # [2025-03-14T09:00:00Z] [ERROR] svc: message
                lines.append(f"[{r.ts.strftime('%Y-%m-%dT%H:%M:%SZ')}] [{r.level}] {r.service}: {r.message}")
        return "\n".join(lines) + "\n"

    def _obj(self, r: Row, style: str) -> dict:
        iso = r.ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{r.ts.microsecond // 1000:03d}Z"
        if style == "pino":  # numeric levels + epoch-millis time
            lvl = {"INFO": 30, "WARNING": 40, "ERROR": 50, "CRITICAL": 60}[r.level]
            return {"level": lvl, "time": int(r.ts.timestamp() * 1000), "name": r.service, "msg": r.message, **r.extra}
        if style == "alias":  # different key names, WARN spelling
            lvl = {"WARNING": "WARN"}.get(r.level, r.level)
            return {"time": iso, "severity": lvl, "app": r.service, "msg": r.message, **r.extra}
        lvl = {"INFO": "info", "WARNING": "warn", "ERROR": "error", "CRITICAL": "fatal"}[r.level]
        return {"timestamp": iso, "level": lvl, "service": r.service, "message": r.message, **r.extra}

    def to_jsonl(self, mixed: dict[str, str] | None = None, default_style: str = "standard") -> str:
        """JSON lines. ``mixed`` maps service -> style to exercise key/level normalization."""
        mixed = mixed or {}
        return "\n".join(
            json.dumps(self._obj(r, mixed.get(r.service, default_style)), ensure_ascii=False)
            for r in self.sorted_rows()
        ) + "\n"

    def to_json(self, style: str = "alias") -> str:
        return json.dumps([self._obj(r, style) for r in self.sorted_rows()], ensure_ascii=False, indent=1) + "\n"
