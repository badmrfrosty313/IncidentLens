"""Stage 2 - redaction: remove common secrets before normalization and analysis.

Redaction is pattern based and therefore best-effort; see docs/SECURITY.md for what it
does and does not cover. Patterns are anchored or bounded so that adversarial input
cannot trigger quadratic backtracking (covered by a test).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .parsing import RawRecord


@dataclass(frozen=True)
class _Rule:
    name: str
    pattern: re.Pattern[str]
    repl: str | Callable[[re.Match[str]], str]
    hint: Callable[[str, str], bool]  # cheap pre-check: (text, lowered_text) -> may match


def _always(_t: str, _l: str) -> bool:
    return True


_SECRET_WORDS = ("passw", "pwd", "secret", "token", "key", "credential")

RULES: tuple[_Rule, ...] = (
    _Rule(
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]{0,30}PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z ]{0,30}PRIVATE KEY(?: BLOCK)?-----|$)", re.DOTALL),
        "[REDACTED_PRIVATE_KEY]",
        lambda t, _l: "PRIVATE KEY" in t,
    ),
    _Rule(
        "authorization_header",
        re.compile(
            r"(authorization[\"']?\s*[:=]\s*[\"']?)(?:(?:bearer|basic|token|digest|negotiate|apikey)\s+)?[^\s\"',;}]+",
            re.IGNORECASE,
        ),
        lambda m: m.group(1) + "[REDACTED_AUTH_HEADER]",
        lambda _t, low: "authorization" in low,
    ),
    _Rule(
        "database_credentials",
        re.compile(r"\b([a-z][a-z0-9+.\-]{0,30}://)[^\s/:@]*:[^\s/]*@", re.IGNORECASE),
        lambda m: m.group(1) + "[REDACTED_CREDENTIALS]@",
        lambda t, _l: "://" in t and "@" in t,
    ),
    _Rule(
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*"),
        "[REDACTED_JWT]",
        lambda t, _l: "eyJ" in t,
    ),
    _Rule(
        "bearer_token",
        re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
        "Bearer [REDACTED_TOKEN]",
        lambda _t, low: "bearer" in low,
    ),
    _Rule(
        "api_key",
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{16,}"
            r"|(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{12,}"
            r"|(?:AKIA|ASIA)[0-9A-Z]{16}"
            r"|gh[pousr]_[A-Za-z0-9]{30,}"
            r"|github_pat_[A-Za-z0-9_]{20,}"
            r"|xox[abprs]-[A-Za-z0-9-]{10,}"
            r"|AIza[0-9A-Za-z_-]{30,}"
            r"|glpat-[A-Za-z0-9_-]{16,}"
            r"|npm_[A-Za-z0-9]{30,})"
        ),
        "[REDACTED_API_KEY]",
        _always,
    ),
    _Rule(
        "secret_assignment",
        re.compile(
            r"((?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|credential)[\w.-]{0,32}(?:\\?[\"'])?\s*[:=]\s*)"
            # quoted values may be JSON-escaped (\") or unterminated (clipped line): take them to the end
            r"(?!\[REDACTED)(?:\\?\"(?:[^\"\\]|\\[^\"])*(?:\\?\"|$)|'[^']*(?:'|$)|[^\s,;&}\])\"']+)",
            re.IGNORECASE,
        ),
        lambda m: m.group(1) + "[REDACTED]",
        lambda _t, low: any(w in low for w in _SECRET_WORDS),
    ),
    _Rule(
        "email",
        re.compile(
            r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}"
        ),
        "[REDACTED_EMAIL]",
        lambda t, _l: "@" in t,
    ),
)

REDACTION_CATEGORIES: tuple[str, ...] = tuple(r.name for r in RULES)


def redact_text(text: str, counts: dict[str, int] | None = None) -> str:
    """Redact one string. When ``counts`` is given, per-category totals are added to it."""
    low = text.lower()
    for rule in RULES:
        if not rule.hint(text, low):
            continue
        text, n = rule.pattern.subn(rule.repl, text)  # type: ignore[arg-type]
        if n:
            if counts is not None:
                counts[rule.name] = counts.get(rule.name, 0) + n
            low = text.lower()
    return text


def redact_records(records: list[RawRecord], counts: dict[str, int] | None = None) -> dict[str, int]:
    """Redact message and service fields of every record in place; returns category totals."""
    totals: dict[str, int] = {} if counts is None else counts
    for rec in records:
        rec.message = redact_text(rec.message, totals)
        if rec.service:
            rec.service = redact_text(rec.service, totals)
    return totals
