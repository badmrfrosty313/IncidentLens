"""Quoted / escaped secret values, malformed strings, and backtracking bounds (Sprint 3)."""

import time

import pytest

from app.pipeline import analyze_text
from app.redaction import redact_text

BS = "\\"


@pytest.mark.parametrize(
    ("text", "gone", "kept"),
    [
        # single escaping: an escaped quote inside a quoted value does not end the value
        (f'password="Xpa{BS}"ss word" after', ["ss word", "Xpa"], ["after"]),
        (f"password='Xit{BS}'s secret' after", ["s secret", "Xit"], ["after"]),
        (f'api_key = "Xab{BS}"Xcd{BS}"Xef" tail', ["Xab", "Xcd", "Xef"], ["tail"]),
        # escaped backslash right before the closing quote still closes the value
        (f'password="end{BS}{BS}" after', ["end"], ["after"]),
        # value that sits inside a JSON string (delimiters are escaped quotes)
        (f'{{"msg":"retry {BS}"password{BS}":{BS}"hunter2 x{BS}" failed"}}', ["hunter2"], ["failed"]),
        # double escaping: the inner quote appears as backslash-backslash-backslash-quote
        (f'{{"msg":"retry {BS}"password{BS}":{BS}"Xpa{BS}{BS}{BS}"ss word{BS}" failed"}}', ["ss word", "Xpa"], ["failed"]),
        (f'{{"msg":"{BS}"token{BS}":{BS}"Xa{BS}{BS}{BS}"Xb{BS}{BS}{BS}"Xc{BS}"}}', ["Xa", "Xb", "Xc"], []),
        # malformed / unterminated values are taken to the end of the text
        ('login password="never closed secret', ["never closed", "secret"], ["login"]),
        ("login token='never closed secret", ["never closed"], ["login"]),
        (f'login password="ends with backslash{BS}', ["ends with"], ["login"]),
        (f'login password={BS}"unterminated escaped secret', ["unterminated"], ["login"]),
        ('password="', [], ["password="]),
        # adjacent fields must survive: redaction must not over-reach past the closing quote
        ('password="x y" user="bob" level=info', ["x y"], ['user="bob"', "level=info"]),
        ("secret: hunter2, next=1", ["hunter2"], ["next=1"]),
    ],
)
def test_quoted_and_escaped_secret_values(text, gone, kept):
    out = redact_text(text)
    for fragment in gone:
        assert fragment not in out.replace("[REDACTED]", ""), (text, out)
    assert "[REDACTED]" in out
    for fragment in kept:
        assert fragment in out, (text, out)


def test_redaction_is_idempotent_on_escaped_values():
    once = redact_text(f'password="Xpa{BS}"ss word" after')
    assert redact_text(once) == once


@pytest.mark.parametrize(
    "payload",
    [
        'password="' + (BS + '"') * 60_000,
        'password="' + BS * 120_001,
        f"password={BS}\"" + (BS * 3 + '"') * 30_000,
        f"password={BS}\"" + BS * 100_001,
        "token='" + (BS + "'") * 60_000,
        'password="' + "a" * 200_000,
        'password="a' + (BS * 2 + '"x') * 30_000,
        "password=" + '"' * 100_000,
        "password=" + (BS + '"') * 100_000,
        ("password=\"a\" " * 20_000),
    ],
    ids=["escaped-quotes", "backslash-run-even", "escaped-delims-triple", "escaped-delims-backslash-run",
         "single-quote-escapes", "long-unterminated", "mixed-pairs", "quote-run", "escaped-quote-run", "many-assignments"],
)
def test_quoted_value_patterns_do_not_backtrack_catastrophically(payload):
    start = time.perf_counter()
    redact_text(payload)
    assert time.perf_counter() - start < 1.0


def test_escaped_secret_in_a_real_pipeline_run_does_not_leak():
    logs = (
        f'2025-03-14T09:00:00Z ERROR [auth] bad login password="hunter2{BS}"extra tail" for user\n'
        '{"timestamp":"2025-03-14T09:00:01Z","level":"error","service":"auth","message":"retry password=\\"s3cr3t value\\" failed"}\n'
    )
    result = analyze_text(logs)
    dump = result.model_dump_json()
    for fragment in ("hunter2", "extra tail", "s3cr3t", "value"):
        assert fragment not in dump.replace("evidence", "")  # "value" must not appear from the secret


def test_long_private_key_body_is_never_kept_and_the_discard_is_reported():
    body = "\n".join(f"QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo{i:05d}SECRETKEYMATERIAL" for i in range(1500))
    text = f"2025-03-14 09:00:00 ERROR svc key\n-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----\n2025-03-14 09:00:02 INFO svc done\n"
    result = analyze_text(text)
    assert "SECRETKEYMATERIAL" not in result.model_dump_json()
    assert result.summary.total_events == 2 and result.ingest.malformed_records == 0
    assert any("private-key" in w for w in result.ingest.warnings)


def test_private_key_without_markers_is_not_recognised():
    """Documented limit: bare base64 without a BEGIN marker is not treated as key material."""
    text = "2025-03-14 09:00:00 ERROR svc key\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC\n"
    result = analyze_text(text)
    assert result.ingest.malformed_records == 1
