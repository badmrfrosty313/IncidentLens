from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import LogEvent, Severity

T0 = datetime(2025, 3, 14, 9, 0, 0, tzinfo=timezone.utc)


def ev(i: int, offset: float, sev: str, svc: str, msg: str) -> LogEvent:
    return LogEvent(
        id=i, line_number=i + 1, timestamp=T0 + timedelta(seconds=offset),
        severity=Severity(sev), service=svc, message=msg,
    )


def numbered(events: list[LogEvent]) -> list[LogEvent]:
    for i, e in enumerate(events):
        e.id = i
    return events
