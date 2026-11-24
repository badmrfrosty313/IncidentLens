#!/usr/bin/env bash
# HTTP smoke test for a running IncidentLens stack (default: docker compose on :8080).
# Not a browser test: it checks that nginx serves the UI shell and proxies a working API,
# including the hardening behaviours (sanitized 422, no secret echo).
set -euo pipefail

BASE="${1:-http://localhost:8080}"
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

echo "waiting for $BASE ..."
for _ in $(seq 1 60); do
  if curl -fsS "$BASE/api/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "$BASE/api/health" | grep -q '"status":"ok"' || fail "/api/health"

curl -fsS "$BASE/" | grep -qi '<div id="root"' || fail "UI shell missing #root"
curl -fsS "$BASE/api/demo" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert len(d) >= 6, len(d)' || fail "/api/demo"
curl -fsS "$BASE/api/demo/db-pool-exhaustion" \
  | python3 -c 'import json,sys; a=json.load(sys.stdin)["analysis"]; assert a["verdict"]=="incident_detected"; assert a["hypotheses"][0]["category"]=="db_pool_exhaustion", a["hypotheses"][0]["category"]' \
  || fail "demo analysis"

body=$(curl -sS -o /tmp/smoke_analyze.json -w '%{http_code}' "$BASE/api/analyze" -H 'content-type: application/json' \
  -d '{"content":"2025-03-14T09:00:00Z ERROR [a] login failed password=hunter2supersecret"}')
[ "$body" = "200" ] || fail "analyze returned $body"
grep -q hunter2supersecret /tmp/smoke_analyze.json && fail "secret leaked in analyze response"

code=$(curl -sS -o /tmp/smoke_422.json -w '%{http_code}' "$BASE/api/analyze" -H 'content-type: application/json' \
  -d '{"content":{"password":"hunter2supersecret"}}')
[ "$code" = "422" ] || fail "validation error returned $code"
grep -q hunter2supersecret /tmp/smoke_422.json && fail "secret echoed in validation error"

echo "SMOKE OK"
