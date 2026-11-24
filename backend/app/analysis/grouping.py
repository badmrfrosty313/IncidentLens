"""Error grouping by message signature and recurring-exception detection."""

from __future__ import annotations

import re
from collections import Counter
from ..models import SEVERITY_RANK, ErrorGroup, ExceptionPattern, LogEvent, Severity

_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b(?:0x)?[0-9a-fA-F]{8,}\b")
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_NUM = re.compile(r"(?<![A-Za-z_\d.])\d+(?:\.\d+)?")
_WS = re.compile(r"\s+")
_EXC = re.compile(r"\b((?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:Exception|Error|Timeout|Failure))\b")


def _num_repl(m: re.Match[str]) -> str:
    text = m.group(0)
    nxt = m.string[m.end() : m.end() + 1]
    # Keep HTTP-looking 4xx/5xx codes so 500 and 503 stay distinguishable.
    if len(text) == 3 and text[0] in "45" and not nxt.isalpha():
        return text
    return "<n>"


def signature(message: str) -> str:
    """Collapse variable parts (ids, ips, numbers) so similar messages group together."""
    first = message.split("\n", 1)[0][:240]
    s = _UUID.sub("<uuid>", first)
    s = _HEX.sub("<hex>", s)
    s = _IP.sub("<ip>", s)
    s = _NUM.sub(_num_repl, s)
    return _WS.sub(" ", s).strip()


def group_events(events: list[LogEvent], top_n: int = 50) -> list[ErrorGroup]:
    """Group WARNING-and-above events by signature, most frequent first."""
    acc: dict[str, dict] = {}
    for e in events:
        if SEVERITY_RANK[e.severity] < SEVERITY_RANK[Severity.WARNING]:
            continue
        sig = signature(e.message)
        g = acc.get(sig)
        if g is None:
            g = acc[sig] = {
                "count": 0, "sev": e.severity, "services": Counter(),
                "first": None, "last": None, "example": e.message.split("\n", 1)[0][:300],
            }
        g["count"] += 1
        if SEVERITY_RANK[e.severity] > SEVERITY_RANK[g["sev"]]:
            g["sev"] = e.severity
        g["services"][e.service] += 1
        if e.timestamp is not None:
            g["first"] = e.timestamp if g["first"] is None else min(g["first"], e.timestamp)
            g["last"] = e.timestamp if g["last"] is None else max(g["last"], e.timestamp)
    groups = [
        ErrorGroup(
            signature=sig, severity=g["sev"], count=g["count"],
            services=[s for s, _ in g["services"].most_common(5)],
            first_seen=g["first"], last_seen=g["last"], example=g["example"],
        )
        for sig, g in acc.items()
    ]
    groups.sort(key=lambda g: (-g.count, -SEVERITY_RANK[g.severity], g.signature))
    return groups[:top_n]


def exception_patterns(
    events: list[LogEvent], bucket_index: dict[int, int] | None = None, top_n: int = 15
) -> list[ExceptionPattern]:
    """Find exception / error type names that recur. ``bucket_index`` maps event id -> bucket."""
    counts: Counter[str] = Counter()
    services: dict[str, Counter[str]] = {}
    buckets: dict[str, set[int]] = {}
    for e in events:
        if SEVERITY_RANK[e.severity] < SEVERITY_RANK[Severity.WARNING]:
            continue
        for name in set(_EXC.findall(e.message[:600])):
            counts[name] += 1
            services.setdefault(name, Counter())[e.service] += 1
            if bucket_index is not None and e.id in bucket_index:
                buckets.setdefault(name, set()).add(bucket_index[e.id])
    out = []
    for name, n in counts.most_common(top_n):
        present = len(buckets.get(name, ()))
        recurring = n >= 3 and (present >= 3 if bucket_index is not None and name in buckets else True)
        out.append(
            ExceptionPattern(
                name=name, count=n, services=[s for s, _ in services[name].most_common(5)],
                buckets_present=present, recurring=recurring,
            )
        )
    return out
