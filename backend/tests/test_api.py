"""HTTP API tests. Require fastapi + httpx (see requirements-dev.txt); skipped otherwise."""

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import DEFAULT_LIMITS  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
LOGS = "".join(f"2025-03-14T09:00:{i % 60:02d}Z INFO [a] hello {i}\n" for i in range(10))


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_analyze_happy_path():
    r = client.post("/api/analyze", json={"content": LOGS})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total_events"] == 10 and body["ingest"]["detected_format"] == "plaintext"
    assert body["verdict"] == "no_incident"


def test_analyze_validation_errors():
    assert client.post("/api/analyze", json={}).status_code == 422
    assert client.post("/api/analyze", json={"content": ""}).status_code == 422
    assert client.post("/api/analyze", json={"content": "x", "format": "xml"}).status_code == 422
    r = client.post("/api/analyze", json={"content": "   \n  "})
    assert r.status_code == 422 and r.json()["code"] == "empty_input"
    assert client.post("/api/analyze", content="not json", headers={"content-type": "application/json"}).status_code == 422


def test_forced_json_on_non_json_is_a_422():
    r = client.post("/api/analyze", json={"content": "plain text", "format": "json"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_input"


def test_oversized_content_is_rejected_with_413():
    big = "x" * (DEFAULT_LIMITS.max_input_bytes + 1)
    r = client.post("/api/analyze", json={"content": big})
    assert r.status_code == 413 and r.json()["code"] == "input_too_large"


def test_oversized_request_body_is_rejected_by_middleware():
    r = client.post("/api/analyze", content=b"x" * 10, headers={"content-type": "application/json", "content-length": str(DEFAULT_LIMITS.max_input_bytes * 3)})
    assert r.status_code == 413


def test_demo_list_and_run():
    listing = client.get("/api/demo").json()
    assert len(listing) >= 6 and all("expected" in s for s in listing)
    r = client.get("/api/demo/db-pool-exhaustion")
    assert r.status_code == 200 and r.json()["analysis"]["hypotheses"][0]["category"] == "db_pool_exhaustion"
    assert client.get("/api/demo/nope").status_code == 404


def test_reports():
    md = client.get("/api/demo/memory-exhaustion/report?format=markdown")
    assert md.status_code == 200 and md.text.startswith("# IncidentLens") and "attachment" in md.headers["content-disposition"]
    js = client.get("/api/demo/memory-exhaustion/report?format=json")
    assert json.loads(js.text)["verdict"] == "incident_detected"
    assert client.get("/api/demo/memory-exhaustion/report?format=pdf").status_code == 422
    posted = client.post("/api/report?format=markdown", json={"content": LOGS})
    assert posted.status_code == 200 and "## Summary" in posted.text


def test_openapi_documents_required_endpoints():
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/api/health", "/api/analyze", "/api/demo", "/api/demo/{scenario}"):
        assert p in paths
    assert client.get("/docs").status_code == 200
