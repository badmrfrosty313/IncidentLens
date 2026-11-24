"""Stage 1 - parsing: turn untrusted text into structured raw records.

Parsing only extracts fields. Nothing here is persisted, and the records it returns are
passed through the redaction stage before any normalization or analysis happens.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .config import DEFAULT_LIMITS, Limits
from .errors import InvalidInputError, TooManyEventsError
from .models import LogFormat, MalformedRecord


@dataclass
class RawRecord:
    line_number: int
    timestamp: Any  # str | int | float | None
    severity: Any  # str | int | None
    service: str | None
    message: str


@dataclass
class ParseResult:
    format: LogFormat
    records: list[RawRecord] = field(default_factory=list)
    malformed: list[MalformedRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- plaintext

_TS = r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})?"
_LEVEL = r"(?:TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERR(?:OR)?|CRIT(?:ICAL)?|FATAL|SEVERE|PANIC)"

_LINE_TS = re.compile(rf"^\s*\[?(?P<ts>{_TS})\]?[\s,;|-]*(?P<rest>.*)$")
_LEVEL_FIRST = re.compile(rf"^\[?(?P<lvl>{_LEVEL})(?:\]|\b)[:\s|-]*(?P<tail>.*)$", re.IGNORECASE)
_SVC_THEN_LEVEL = re.compile(
    rf"^\[?(?P<svc>[\w.\-/]{{1,64}})\]?\s+\[?(?P<lvl>{_LEVEL})(?:\]|\b)[:\s|-]*(?P<msg>.*)$",
    re.IGNORECASE,
)
_SVC_BRACKET = re.compile(r"^\[(?P<svc>[^\]\s]{1,64})\]\s*[:\-|]?\s*(?P<msg>.*)$")
_SVC_COLON = re.compile(r"^(?P<svc>[a-z][\w.\-/]{0,63})\s*(?::|\s-\s|\s\|\s)\s*(?P<msg>.*)$")
_LEVEL_ONLY = re.compile(rf"^\[?(?P<lvl>{_LEVEL})(?:\]|\b)[:\s|-]*(?P<tail>.*)$")  # case-sensitive
_CONTINUATION = re.compile(
    r"^(?:\s+\S|at\s|Caused by\b|Traceback \(|File \"|\.\.\. \d+|(?:[A-Za-z_][\w.]*)?(?:Error|Exception)\b)"
)


def _split_service(tail: str) -> tuple[str | None, str]:
    m = _SVC_BRACKET.match(tail)
    if m:
        return m.group("svc"), m.group("msg")
    m = _SVC_COLON.match(tail)
    if m:
        return m.group("svc"), m.group("msg")
    return None, tail


def _parse_plain_line(line: str) -> RawRecord | None:
    """Parse one timestamped line. Returns None when the line has no timestamp."""
    m = _LINE_TS.match(line)
    if not m:
        return None
    ts, rest = m.group("ts"), m.group("rest").strip()
    lm = _LEVEL_FIRST.match(rest)
    if lm:
        svc, msg = _split_service(lm.group("tail").strip())
        return RawRecord(0, ts, lm.group("lvl"), svc, msg)
    sm = _SVC_THEN_LEVEL.match(rest)
    if sm:
        return RawRecord(0, ts, sm.group("lvl"), sm.group("svc"), sm.group("msg"))
    svc, msg = _split_service(rest)
    return RawRecord(0, ts, None, svc, msg)


def safe_clip(text: str, limit: int) -> tuple[str, bool]:
    """Clip ``text`` to ``limit`` characters without leaving a half-cut token behind.

    Clipping happens before redaction (the length bound is what keeps redaction cheap), so a
    secret straddling the cut would otherwise survive as a prefix too short for any pattern to
    recognise. The partial trailing token is therefore dropped; if the cut lands inside the only
    token, nothing is kept.
    """
    if len(text) <= limit:
        return text, False
    if text[limit].isspace():
        return text[:limit].rstrip(), True
    cut = text[:limit]
    i = len(cut)
    while i > 0 and not cut[i - 1].isspace():
        i -= 1
    return cut[:i].rstrip(), True


_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z ]{0,30}PRIVATE KEY(?: BLOCK)?-----")
_PEM_END = re.compile(r"-----END [A-Z ]{0,30}PRIVATE KEY(?: BLOCK)?-----")


def _check_count(n: int, limits: Limits) -> None:
    if n > limits.max_events:
        raise TooManyEventsError(
            f"Input contains more than {limits.max_events:,} records. "
            "Split the file or raise INCIDENTLENS_MAX_EVENTS."
        )


def parse_plaintext(text: str, limits: Limits = DEFAULT_LIMITS) -> ParseResult:
    result = ParseResult(format="plaintext")
    prev: RawRecord | None = None
    continuation = 0
    clipped = 0
    key_lines = -1  # >= 0 while inside a PEM private-key block
    key_discarded = 0
    for number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        if key_lines >= 0:
            # Key bodies are bare base64 lines that match no log shape; without this they would be
            # kept as "malformed" samples, outside the reach of the multi-line private-key rule.
            ends = _PEM_END.search(raw_line) is not None
            # No length cap: a cap would turn the rest of a long key into "malformed" samples. The block
            # ends at its END marker or at the next timestamped record, whichever comes first.
            if ends or _parse_plain_line(raw_line[: limits.max_line_chars]) is not None:
                key_lines = -1
                if ends:
                    key_discarded += 1
                    continue
            else:
                key_lines += 1
                key_discarded += 1
                continue
        line, was_clipped = safe_clip(raw_line.replace("\x00", ""), limits.max_line_chars)
        clipped += was_clipped
        rec = _parse_plain_line(line)
        if rec is not None:
            rec.line_number = number
            result.records.append(rec)
            prev, continuation = rec, 0
        elif prev is not None and (_CONTINUATION.match(line) or _PEM_BEGIN.search(line)):
            if continuation < limits.max_continuation_lines and len(prev.message) < limits.max_line_chars:
                prev.message += "\n" + line.strip()
                continuation += 1
        else:
            lv = _LEVEL_ONLY.match(line.strip())
            if lv:
                svc, msg = _split_service(lv.group("tail").strip())
                rec = RawRecord(number, None, lv.group("lvl"), svc, msg)
                result.records.append(rec)
                prev, continuation = rec, 0
            else:
                result.malformed.append(
                    MalformedRecord(line_number=number, reason="no timestamp or severity found", sample=safe_clip(line, 200)[0])
                )
                prev = None
        if key_lines < 0 and _PEM_BEGIN.search(line) and not _PEM_END.search(line):
            key_lines = 0
        _check_count(len(result.records) + len(result.malformed), limits)
    if key_discarded:
        result.warnings.append(
            f"{key_discarded} line(s) inside PEM private-key block(s) were discarded without being kept or analyzed."
        )
    if clipped:
        result.warnings.append(f"{clipped} over-long line(s) were clipped at {limits.max_line_chars:,} characters.")
    return result


# ----------------------------------------------------------------------------- JSON

_TS_KEYS = ("timestamp", "@timestamp", "time", "ts", "datetime", "date", "t")
_SEV_KEYS = ("level", "severity", "lvl", "log_level", "loglevel", "levelname", "severity_text")
_SVC_KEYS = ("service", "service_name", "servicename", "app", "application", "component", "logger", "source", "name")
_MSG_KEYS = ("message", "msg", "text", "log", "event", "description")
_ERR_KEYS = ("error", "err", "exception", "stack", "stacktrace", "stack_trace", "reason")
_STATUS_KEYS = ("status", "status_code", "statuscode", "http_status")
_LIST_KEYS = ("events", "logs", "records", "entries", "items", "data")


def _first(m: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in m and m[k] is not None:
            return m[k]
    return None


def _stringify(v: Any, cap: int = 1000) -> str:
    if isinstance(v, str):
        return safe_clip(v, cap)[0]
    if isinstance(v, dict):
        parts = [str(v[k]) for k in ("type", "name", "code", "message", "stack") if k in v and v[k] is not None]
        if parts:
            return safe_clip(" ".join(parts), cap)[0]
    try:
        return safe_clip(json.dumps(v, ensure_ascii=False, default=str), cap)[0]
    except (TypeError, ValueError, RecursionError):
        return safe_clip(str(v), cap)[0]


def _record_from_obj(obj: Any, number: int) -> RawRecord | MalformedRecord:
    if isinstance(obj, str):
        rec = _parse_plain_line(obj.strip())
        if rec is None:
            return MalformedRecord(line_number=number, reason="string entry has no timestamp", sample=safe_clip(obj, 200)[0])
        rec.line_number = number
        return rec
    if not isinstance(obj, dict):
        return MalformedRecord(line_number=number, reason=f"expected an object, got {type(obj).__name__}", sample=_stringify(obj, 200))
    m = {k.lower(): v for k, v in obj.items() if isinstance(k, str)}
    msg_val = _first(m, _MSG_KEYS)
    message = _stringify(msg_val) if msg_val is not None else ""
    for key in _ERR_KEYS:
        if key in m and m[key] is not None:
            extra = _stringify(m[key])
            if extra and extra not in message:
                message = f"{message} | {key}: {extra}" if message else f"{key}: {extra}"
    status = _first(m, _STATUS_KEYS)
    if isinstance(status, (int, str)) and str(status).isdigit() and "status" not in message.lower():
        message = f"{message} status={status}".strip()
    if not message:
        return MalformedRecord(line_number=number, reason="no message field", sample=_stringify(obj, 200))
    svc = _first(m, _SVC_KEYS)
    return RawRecord(
        line_number=number,
        timestamp=_first(m, _TS_KEYS),
        severity=_first(m, _SEV_KEYS),
        service=svc if isinstance(svc, str) else None,
        message=message,
    )


def _from_items(items: list[Any], fmt: LogFormat, limits: Limits) -> ParseResult:
    _check_count(len(items), limits)
    result = ParseResult(format=fmt)
    for i, item in enumerate(items, start=1):
        out = _record_from_obj(item, i)
        (result.records if isinstance(out, RawRecord) else result.malformed).append(out)  # type: ignore[arg-type]
    return result


def parse_jsonl(text: str, limits: Limits = DEFAULT_LIMITS) -> ParseResult:
    result = ParseResult(format="jsonl")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if len(line) > limits.max_line_chars:
            result.malformed.append(
                MalformedRecord(line_number=number, reason="line exceeds maximum length", sample=safe_clip(line, 200)[0])
            )
        else:
            try:
                obj = json.loads(line)
            except (ValueError, RecursionError):
                result.malformed.append(MalformedRecord(line_number=number, reason="invalid JSON", sample=safe_clip(line, 200)[0]))
            else:
                out = _record_from_obj(obj, number)
                (result.records if isinstance(out, RawRecord) else result.malformed).append(out)  # type: ignore[arg-type]
        _check_count(len(result.records) + len(result.malformed), limits)
    return result


def _json_document_items(doc: Any) -> list[Any] | None:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for key in _LIST_KEYS:
            if isinstance(doc.get(key), list):
                return doc[key]
    return None


def _load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        return None


def detect_format(text: str) -> LogFormat:
    """Detect plaintext / JSON document / JSONL from the content alone."""
    head = text.lstrip()
    if head.startswith(("[", "{")):
        doc = _load_json(text)
        if doc is not None and _json_document_items(doc) is not None:
            return "json"
        if isinstance(doc, dict):
            return "jsonl"  # a single JSON object on its own
        lines = [ln for ln in text.splitlines() if ln.strip()][:25]
        ok = sum(1 for ln in lines if ln.lstrip().startswith("{") and _load_json(ln) is not None)
        if lines and ok / len(lines) >= 0.6:
            return "jsonl"
    return "plaintext"


def parse_logs(text: str, format_hint: str = "auto", limits: Limits = DEFAULT_LIMITS) -> ParseResult:
    fmt: str = detect_format(text) if format_hint == "auto" else format_hint
    if fmt == "json":
        doc = _load_json(text)
        items = _json_document_items(doc) if doc is not None else None
        if items is None:
            raise InvalidInputError(
                "Input is not a JSON array (or an object with an events/logs/records list)."
            )
        return _from_items(items, "json", limits)
    if fmt == "jsonl":
        return parse_jsonl(text, limits)
    if fmt == "plaintext":
        return parse_plaintext(text, limits)
    raise InvalidInputError(f"Unsupported format: {format_hint!r}")
