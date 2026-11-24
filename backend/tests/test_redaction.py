import time

import pytest

from app.pipeline import analyze_text
from app.redaction import redact_text

JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"


@pytest.mark.parametrize(
    "raw,secret,category",
    [
        ("login password=hunter2 ok", "hunter2", "secret_assignment"),
        ('{"password": "s3cr3t-value"}', "s3cr3t-value", "secret_assignment"),
        ("api_key: abcd1234efgh5678", "abcd1234efgh5678", "secret_assignment"),
        ("client_secret='topsecretvalue'", "topsecretvalue", "secret_assignment"),
        ("Authorization: Bearer abc.def.ghi-123456", "abc.def.ghi-123456", "authorization_header"),
        ("authorization=Basic dXNlcjpwYXNz", "dXNlcjpwYXNz", "authorization_header"),
        ('"Proxy-Authorization": "Basic dXNlcjpwYXNz"', "dXNlcjpwYXNz", "authorization_header"),
        (f"token was {JWT} here", JWT, "jwt"),
        ("sent Bearer abcdefgh12345678 to upstream", "abcdefgh12345678", "bearer_token"),
        ("key sk-live0123456789abcdefghij used", "sk-live0123456789abcdefghij", "api_key"),
        ("aws AKIAIOSFODNN7EXAMPLE leaked", "AKIAIOSFODNN7EXAMPLE", "api_key"),
        ("gh ghp_" + "a" * 36, "ghp_" + "a" * 36, "api_key"),
        ("mail alice.smith+tag@example.co.uk failed", "alice.smith+tag@example.co.uk", "email"),
        ("connect postgres://app:p%40ss:w0rd@db.internal:5432/orders failed", "p%40ss:w0rd", "database_credentials"),
        ("redis://:onlypass@cache:6379", "onlypass", "database_credentials"),
        ("mongodb+srv://user:pa@ss@cluster0.example.net/db", "pa@ss", "database_credentials"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\n-----END RSA PRIVATE KEY-----", "MIIEabc", "private_key"),
    ],
)
def test_secret_is_removed_and_counted(raw, secret, category):
    counts: dict[str, int] = {}
    out = redact_text(raw, counts)
    assert secret not in out, out
    assert "REDACTED" in out
    assert counts.get(category, 0) >= 1, (counts, out)


def test_non_sensitive_text_is_unchanged():
    msg = "GET /api/v1/orders 200 12ms request_id=abc123 user clicked token expired page"
    assert redact_text(msg) == msg


def test_redacted_markers_are_not_double_redacted():
    out = redact_text(f"token={JWT}")
    assert out == "token=[REDACTED_JWT]"


def test_redaction_survives_clipping_boundary():
    # A secret straddling the line limit must not remain partially visible.
    from app.config import Limits

    secret = "sk-" + "a1B2" * 12
    line = "2025-03-14T09:00:00Z ERROR [a] " + "x" * 80 + " " + secret
    cut = len("2025-03-14T09:00:00Z ERROR [a] ") + 80 + 1 + 20
    result = analyze_text(line, limits=Limits(max_line_chars=cut))
    assert "a1B2" not in result.events[0].message


def test_end_to_end_no_secret_reaches_response_or_report():
    from app.reporting import render_json, render_markdown

    text = (
        "2025-03-14T09:00:00Z ERROR [auth] login failed for bob@example.com password=Sup3rS3cret\n"
        "2025-03-14T09:00:01Z ERROR [auth] Authorization: Bearer abcdef1234567890 rejected\n"
        f"2025-03-14T09:00:02Z ERROR [auth] jwt {JWT} invalid token\n"
        "2025-03-14T09:00:03Z ERROR [auth] db postgres://svc:DbPassw0rd@db:5432/x unreachable\n"
        "2025-03-14T09:00:04Z INFO [auth] ok\n"
    )
    result = analyze_text(text)
    blob = result.model_dump_json() + render_markdown(result) + render_json(result)
    for secret in ("bob@example.com", "Sup3rS3cret", "abcdef1234567890", JWT, "DbPassw0rd"):
        assert secret not in blob, secret
    assert result.ingest.redactions


def test_secrets_in_malformed_samples_are_redacted():
    text = "2025-03-14T09:00:00Z INFO [a] ok\nBROKEN line with password=LeakyLeaky99\n"
    result = analyze_text(text)
    assert result.ingest.malformed_records == 1
    assert "LeakyLeaky99" not in result.model_dump_json()


def test_json_fields_are_redacted():
    text = '{"timestamp":"2025-03-14T09:00:00Z","level":"error","service":"a","message":"x","error":"token=abc123secret failed"}\n'
    result = analyze_text(text)
    assert "abc123secret" not in result.events[0].message


@pytest.mark.parametrize("payload", ["a" * 8000, "a@" * 4000, "password" * 1000, "://" * 2000, ("x" * 60 + ".") * 120, "eyJ" + "a." * 3000])
def test_adversarial_lines_do_not_cause_catastrophic_backtracking(payload):
    start = time.perf_counter()
    redact_text(payload)
    assert time.perf_counter() - start < 1.0
