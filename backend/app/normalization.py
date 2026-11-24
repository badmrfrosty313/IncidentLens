"""Stage 3 - normalization: timestamps, severity, service names and messages."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from .config import DEFAULT_LIMITS, Limits
from .models import IngestStats, LogEvent, Severity
from .parsing import RawRecord

_SEVERITY_NAMES: dict[str, Severity] = {
    "TRACE": Severity.DEBUG, "DEBUG": Severity.DEBUG, "VERBOSE": Severity.DEBUG,
    "INFO": Severity.INFO, "INFORMATION": Severity.INFO, "NOTICE": Severity.INFO, "LOG": Severity.INFO,
    "WARN": Severity.WARNING, "WARNING": Severity.WARNING,
    "ERR": Severity.ERROR, "ERROR": Severity.ERROR, "SEVERE": Severity.ERROR, "EXCEPTION": Severity.ERROR,
    "CRIT": Severity.CRITICAL, "CRITICAL": Severity.CRITICAL, "FATAL": Severity.CRITICAL,
    "PANIC": Severity.CRITICAL, "EMERG": Severity.CRITICAL, "EMERGENCY": Severity.CRITICAL, "ALERT": Severity.CRITICAL,
}
_SYSLOG = {0: Severity.CRITICAL, 1: Severity.CRITICAL, 2: Severity.CRITICAL, 3: Severity.ERROR,
           4: Severity.WARNING, 5: Severity.INFO, 6: Severity.INFO, 7: Severity.DEBUG}

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SERVICE_BAD = re.compile(r"[^a-z0-9._/-]+")


_NUMERIC_LEVEL = re.compile(r"[0-9]{1,4}")  # ASCII digits only: str.isdigit() also accepts e.g. "²"
_MAX_NUMERIC_LEVEL = 1000


def normalize_severity(value: Any) -> Severity | None:
    """Map a raw level (name, syslog number or pino-style number) to Severity; None if unknown.

    Malformed numerics (NaN, infinity, absurdly long or non-ASCII digit strings, out-of-range
    values) are treated as an unknown level and never raise.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if _NUMERIC_LEVEL.fullmatch(text):
            value = int(text)
        else:
            return _SEVERITY_NAMES.get(text.upper())
    if isinstance(value, float):
        if not math.isfinite(value) or not 0 <= value <= _MAX_NUMERIC_LEVEL:
            return None
        value = int(value)
    if isinstance(value, int):
        n = value
        if not 0 <= n <= _MAX_NUMERIC_LEVEL:
            return None
        if n <= 7:
            return _SYSLOG[n]
        if n < 30:
            return Severity.DEBUG
        if n < 40:
            return Severity.INFO
        if n < 50:
            return Severity.WARNING
        if n < 60:
            return Severity.ERROR
        return Severity.CRITICAL
    return None


def parse_timestamp(value: Any) -> tuple[datetime | None, bool]:
    """Return (UTC datetime or None, was_naive). Accepts ISO-8601 strings and epoch s/ms."""
    if value is None or isinstance(value, bool):
        return None, False
    naive = False
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r"\d{9,16}(?:\.\d+)?", value.strip())):
            n = float(value)
            if n > 1e14:  # microseconds
                n /= 1e6
            elif n > 1e11:  # milliseconds
                n /= 1e3
            dt = datetime.fromtimestamp(n, tz=timezone.utc)
        else:
            text = str(value).strip().replace(",", ".")
            text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text) if re.search(r"[+-]\d{4}$", text) else text
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                naive = True
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None, False
    if not (1990 <= dt.year <= 2100):
        return None, False
    return dt, naive


def normalize_service(value: str | None) -> str:
    if not value:
        return "unknown"
    s = _SERVICE_BAD.sub("-", value.strip().lower().replace(" ", "-"))
    s = re.sub(r"-{2,}", "-", s).strip("-._/")[:64]
    return s or "unknown"


def normalize_message(value: str, limit: int) -> tuple[str, bool]:
    text = _CONTROL.sub("", value).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + " …[truncated]", True
    return text, False


def normalize_records(
    records: list[RawRecord], stats: IngestStats, limits: Limits = DEFAULT_LIMITS
) -> list[LogEvent]:
    """Normalize redacted records into time-ordered LogEvents and update ``stats`` counters."""
    staged: list[tuple[datetime | None, int, Severity, str, str]] = []
    for rec in records:
        ts, naive = parse_timestamp(rec.timestamp)
        if ts is None:
            stats.events_without_timestamp += 1
        stats.events_with_naive_timestamp += naive
        sev = normalize_severity(rec.severity)
        if sev is None:
            stats.events_without_severity += 1
            sev = Severity.INFO
        msg, truncated = normalize_message(rec.message, limits.max_message_chars)
        stats.truncated_messages += truncated
        staged.append((ts, rec.line_number, sev, normalize_service(rec.service), msg))
    far = datetime.max.replace(tzinfo=timezone.utc)
    staged.sort(key=lambda r: (r[0] is None, r[0] or far, r[1]))
    events = [
        LogEvent(id=i, line_number=line, timestamp=ts, severity=sev, service=svc, message=msg)
        for i, (ts, line, sev, svc, msg) in enumerate(staged)
    ]
    if stats.events_without_timestamp:
        stats.warnings.append(
            f"{stats.events_without_timestamp} event(s) have no usable timestamp; "
            "they are counted but excluded from timeline analysis."
        )
    if stats.events_without_severity:
        stats.warnings.append(
            f"{stats.events_without_severity} event(s) had a missing or unrecognized severity and were treated as INFO."
        )
    if stats.events_with_naive_timestamp:
        stats.warnings.append(
            f"{stats.events_with_naive_timestamp} timestamp(s) had no timezone and were interpreted as UTC."
        )
    return events
