import json

import pytest

from app.config import Limits
from app.errors import InvalidInputError, TooManyEventsError
from app.models import IngestStats, Severity
from app.normalization import normalize_records, normalize_severity, normalize_service, parse_timestamp
from app.parsing import detect_format, parse_logs


def _stats():
    return IngestStats(detected_format="plaintext", input_bytes=0, total_records=0, parsed_records=0, malformed_records=0)


# ----------------------------------------------------------------------------- detection


def test_detect_plaintext_jsonl_and_json():
    assert detect_format("2025-03-14T09:00:00Z INFO [a] hello\n") == "plaintext"
    assert detect_format('{"message":"a"}\n{"message":"b"}\n') == "jsonl"
    assert detect_format('[{"message":"a"},{"message":"b"}]') == "json"
    assert detect_format('{"events":[{"message":"a"}]}') == "json"
    assert detect_format('{"message":"just one"}') == "jsonl"


def test_bracketed_plaintext_is_not_mistaken_for_json():
    assert detect_format("[2025-03-14T09:00:00Z] [ERROR] svc: boom\n") == "plaintext"


# ----------------------------------------------------------------------------- plaintext shapes


@pytest.mark.parametrize(
    "line,service,level,message",
    [
        ("2025-03-14T09:00:00.123Z ERROR [payment-api] card declined", "payment-api", "ERROR", "card declined"),
        ("2025-03-14 09:00:00,123 WARN payment-api - slow call", "payment-api", "WARN", "slow call"),
        ("[2025-03-14T09:00:00Z] [CRITICAL] db: disk full", "db", "CRITICAL", "disk full"),
        ("2025-03-14T09:00:00Z payment-api ERROR timeout", "payment-api", "ERROR", "timeout"),
        ("2025-03-14T09:00:00Z INFO plain message", None, "INFO", "plain message"),
    ],
)
def test_plaintext_shapes(line, service, level, message):
    r = parse_logs(line)
    assert r.format == "plaintext" and not r.malformed
    rec = r.records[0]
    assert (rec.service, rec.severity, rec.message) == (service, level, message)


def test_stack_trace_lines_fold_into_previous_record():
    text = (
        "2025-03-14T09:00:00Z ERROR [api] Unhandled exception\n"
        "Traceback (most recent call last):\n"
        '  File "app.py", line 1, in <module>\n'
        "ValueError: boom\n"
        "2025-03-14T09:00:01Z INFO [api] next\n"
    )
    r = parse_logs(text)
    assert len(r.records) == 2
    assert "Traceback" in r.records[0].message and "File" in r.records[0].message
    assert not r.malformed


def test_malformed_lines_are_counted_not_fatal():
    text = "2025-03-14T09:00:00Z INFO [a] ok\n???? garbage ????\n2025-03-14T09:00:02Z ERROR [a] bad\n"
    r = parse_logs(text)
    assert len(r.records) == 2
    assert len(r.malformed) == 1 and r.malformed[0].line_number == 2


def test_overlong_plaintext_line_is_clipped_with_warning():
    line = "2025-03-14T09:00:00Z ERROR [a] " + "word " * 5000
    r = parse_logs(line, limits=Limits(max_line_chars=1000))
    assert len(r.records[0].message) <= 1000
    assert r.warnings


# ----------------------------------------------------------------------------- JSON / JSONL


def test_jsonl_aliases_and_extra_fields():
    rows = [
        {"@timestamp": "2025-03-14T09:00:00Z", "level": "error", "app": "api", "msg": "failed", "error": {"type": "TimeoutError"}, "status": 504},
        {"time": 1741942801000, "severity": "WARN", "service_name": "api", "text": "slow"},
    ]
    r = parse_logs("\n".join(json.dumps(x) for x in rows))
    assert r.format == "jsonl" and len(r.records) == 2
    first = r.records[0]
    assert first.service == "api" and "TimeoutError" in first.message and "status=504" in first.message


def test_jsonl_malformed_and_missing_message():
    text = '{"message": "ok"}\n{not json}\n{"level": "info"}\n[1,2]\n'
    r = parse_logs(text, "jsonl")
    reasons = {m.reason for m in r.malformed}
    assert len(r.records) == 1
    assert "invalid JSON" in reasons and "no message field" in reasons


def test_json_array_document_and_string_entries():
    doc = json.dumps([{"message": "a", "level": "info"}, "2025-03-14T09:00:00Z ERROR [x] hi", 42])
    r = parse_logs(doc)
    assert r.format == "json" and len(r.records) == 2 and len(r.malformed) == 1


def test_forced_json_on_invalid_document_raises():
    with pytest.raises(InvalidInputError):
        parse_logs("not json at all", "json")


def test_deeply_nested_json_does_not_crash():
    bomb = "[" * 100000 + "]" * 100000
    r = parse_logs(bomb + "\n", "jsonl")
    assert len(r.malformed) == 1


def test_too_many_records_rejected_not_truncated():
    text = "\n".join(f"2025-03-14T09:00:{i % 60:02d}Z INFO [a] m{i}" for i in range(50))
    with pytest.raises(TooManyEventsError):
        parse_logs(text, limits=Limits(max_events=10))


# ----------------------------------------------------------------------------- normalization


def test_severity_normalization():
    cases = {"warn": Severity.WARNING, "FATAL": Severity.CRITICAL, "err": Severity.ERROR, "Information": Severity.INFO,
             50: Severity.ERROR, 30: Severity.INFO, 40: Severity.WARNING, 60: Severity.CRITICAL, 3: Severity.ERROR,
             "20": Severity.DEBUG}
    for raw, want in cases.items():
        assert normalize_severity(raw) == want, raw
    assert normalize_severity("banana") is None and normalize_severity(None) is None


def test_timestamp_normalization():
    iso, naive = parse_timestamp("2025-03-14T09:00:00+02:00")
    assert iso.isoformat() == "2025-03-14T07:00:00+00:00" and not naive
    comma, naive = parse_timestamp("2025-03-14 09:00:00,250")
    assert comma.microsecond == 250000 and naive
    assert parse_timestamp(1741942800)[0] == parse_timestamp(1741942800000)[0]
    assert parse_timestamp("0000-00-00")[0] is None
    assert parse_timestamp("yesterday")[0] is None
    assert parse_timestamp(True)[0] is None


def test_service_normalization():
    assert normalize_service("Payment API!!") == "payment-api"
    assert normalize_service(None) == "unknown" and normalize_service("***") == "unknown"
    assert len(normalize_service("x" * 500)) == 64


def test_events_are_sorted_and_warnings_recorded():
    text = (
        "2025-03-14T09:00:05Z ERROR [a] later\n"
        "2025-03-14T09:00:01Z INFO [a] earlier\n"
        "2025-03-14T09:00:03 [b] no level\n"
        "ERROR [c] no timestamp\n"
    )
    r = parse_logs(text)
    stats = _stats()
    events = normalize_records(r.records, stats)
    assert [e.message for e in events][:2] == ["earlier", "no level"]
    assert events[-1].timestamp is None  # undated events sort last
    assert stats.events_without_timestamp == 1 and stats.events_without_severity == 1 and stats.events_with_naive_timestamp == 1
    assert any("no usable timestamp" in w for w in stats.warnings)


def test_message_truncation_counted():
    r = parse_logs("2025-03-14T09:00:00Z ERROR [a] " + "x" * 500)
    stats = _stats()
    events = normalize_records(r.records, stats, Limits(max_message_chars=100))
    assert events[0].message.endswith("[truncated]") and stats.truncated_messages == 1
