"""HTTP-level regression tests against the real FastAPI app and middleware stack."""

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import DEFAULT_LIMITS  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
SECRET = "hunter2supersecretvalue"
BODY_LIMIT = DEFAULT_LIMITS.max_input_bytes * 2 + 65_536


def _assert_sanitized(response):
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert SECRET not in response.text
    assert all(set(err) == {"loc", "type"} for err in body["errors"])


def test_validation_error_does_not_echo_a_secret_in_a_field_value():
    _assert_sanitized(client.post("/api/analyze", json={"content": f"password={SECRET}", "format": f"password={SECRET}"}))


def test_validation_error_does_not_echo_a_wrongly_typed_content_field():
    _assert_sanitized(client.post("/api/analyze", json={"content": {"password": SECRET}}))


def test_validation_error_does_not_echo_malformed_json_bodies():
    r = client.post("/api/analyze", content=f'{{"content": "password={SECRET}'.encode(), headers={"content-type": "application/json"})
    _assert_sanitized(r)


def test_validation_error_does_not_echo_query_parameters():
    _assert_sanitized(client.post("/api/report", params={"format": f"token={SECRET}"}, json={"content": "x"}))


def test_validation_error_for_empty_content_is_still_helpful():
    r = client.post("/api/analyze", json={"content": ""})
    assert r.status_code == 422 and r.json()["errors"][0]["loc"][-1] == "content"


def test_domain_errors_keep_their_shape():
    r = client.post("/api/analyze", json={"content": "   \n"})
    assert r.status_code == 422 and set(r.json()) == {"code", "detail"}


def _chunks(total: int, size: int = 1 << 20):
    sent = 0
    while sent < total:
        n = min(size, total - sent)
        sent += n
        yield b"a" * n


def test_chunked_upload_over_the_limit_is_413_not_400_or_500():
    r = client.post("/api/analyze", content=_chunks(BODY_LIMIT + (1 << 20)), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert r.json()["code"] == "input_too_large"


def test_chunked_upload_over_the_limit_is_413_on_the_report_endpoint():
    r = client.post("/api/report", content=_chunks(BODY_LIMIT + 1), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_content_length_upload_over_the_limit_is_413():
    r = client.post("/api/analyze", content=b"a" * (BODY_LIMIT + 1), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_chunked_upload_within_the_limit_still_works():
    payload = json.dumps({"content": "2025-03-14T09:00:00Z INFO [a] hello\n"}).encode()
    parts = (payload[i : i + 7] for i in range(0, len(payload), 7))
    r = client.post("/api/analyze", content=parts, headers={"content-type": "application/json"})
    assert r.status_code == 200 and r.json()["summary"]["total_events"] == 1


def test_secrets_never_appear_in_the_analysis_response():
    logs = f"2025-03-14T09:00:00Z ERROR [a] login failed password={SECRET} token=sk-abcdefghijklmnopqrstuvwxyz0123\nnot a log line password: \"{SECRET} x\"\n"
    r = client.post("/api/analyze", json={"content": logs})
    assert r.status_code == 200
    assert SECRET not in r.text and "sk-abcdef" not in r.text
