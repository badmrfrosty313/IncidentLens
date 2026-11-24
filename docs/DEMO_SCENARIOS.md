# Demo scenarios and expected outcomes

All data is **synthetic** and deterministic (seeded generators in `backend/app/demo/scenarios.py`). Datasets are also
exported to `data/demo/` by `python backend/scripts/export_demo_data.py` and can be uploaded through the UI.
Some messages intentionally contain fake emails, passwords and tokens to exercise redaction.

The expected outcomes below are machine-checked by `backend/tests/test_scenarios.py` and
`python backend/scripts/evaluate_demos.py`. The observed numbers are from the current engine.

| Scenario | Format | Events | Expected verdict | Expected severity | Expected top hypothesis | Spike | Cascade |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| `db-pool-exhaustion` | plaintext | 1,613 | incident detected | high | db_pool_exhaustion | yes | no |
| `memory-exhaustion` | jsonl | 1,178 | incident detected | >= high | memory_exhaustion | yes | no |
| `auth-service-failure` | plaintext | 1,505 | incident detected | >= medium | auth_failure | yes | no |
| `network-dependency-timeout` | plaintext | 1,528 | incident detected | >= medium | network_timeout | yes | no |
| `cascading-microservice-failure` | jsonl | 2,164 | incident detected | critical | dependency_failure | yes | yes |
| `healthy-system` | plaintext | 1,470 | no incident | none | none | no | no |
| `rate-limit-storm` | json | 1,310 | incident detected | >= medium | rate_limiting | yes | no |

## Database connection pool exhaustion (`db-pool-exhaustion`)

orders-api runs out of database connections; the gateway then returns HTTP 500s.

- **Expected:** Pool-exhaustion errors in orders-api rank first; gateway 5xx is a lower-ranked symptom.
- **Required hypotheses:** db_pool_exhaustion, http_5xx
- **Forbidden hypotheses:** memory_exhaustion, auth_failure, rate_limiting
- **Required affected services:** orders-api, api-gateway
- **Observed:** verdict `incident_detected`, severity `high`, hypotheses db_pool_exhaustion (84.2), http_5xx (73.3)

## Memory exhaustion (`memory-exhaustion`)

image-processor heap grows until OutOfMemoryError and repeated OOMKilled restarts.

- **Expected:** OOM and heap evidence ranks first; scheduler 'connection refused' is a downstream effect. Mixed JSON key and level styles.
- **Required hypotheses:** memory_exhaustion
- **Forbidden hypotheses:** auth_failure, rate_limiting, db_pool_exhaustion
- **Required affected services:** image-processor, scheduler
- **Observed:** verdict `incident_detected`, severity `high`, hypotheses memory_exhaustion (79.7), dependency_failure (70.3)

## Authentication service failure (`auth-service-failure`)

A signing-key rotation breaks JWT validation; downstream services return HTTP 401.

- **Expected:** Authentication evidence ranks first. Contains fake emails, a password and a JWT that must be redacted.
- **Required hypotheses:** auth_failure
- **Forbidden hypotheses:** memory_exhaustion, db_pool_exhaustion, rate_limiting
- **Required affected services:** auth-service, profile-api, checkout-api
- **Observed:** verdict `incident_detected`, severity `high`, hypotheses auth_failure (89.8)

## Network dependency timeout (`network-dependency-timeout`)

payment-service times out calling an external payment provider; checkout returns 504.

- **Expected:** Timeout, deadline and ETIMEDOUT evidence ranks first.
- **Required hypotheses:** network_timeout
- **Forbidden hypotheses:** memory_exhaustion, auth_failure, db_pool_exhaustion, rate_limiting
- **Required affected services:** payment-service, checkout-api
- **Observed:** verdict `incident_detected`, severity `medium`, hypotheses network_timeout (95.2), http_5xx (73.6), dependency_failure (63.1)

## Cascading microservice failure (`cascading-microservice-failure`)

A database outage propagates through six services in successive waves.

- **Expected:** Cascade detected with inventory-db as origin; dependency failure ranks first.
- **Required hypotheses:** dependency_failure
- **Forbidden hypotheses:** memory_exhaustion, auth_failure, rate_limiting
- **Required affected services:** inventory-db, inventory-service, catalog-service, search-api, api-gateway, web-frontend
- **Observed:** verdict `incident_detected`, severity `critical`, hypotheses dependency_failure (89.5), http_5xx (74.4)

## Healthy system with routine warnings (`healthy-system`)

Normal traffic with routine warnings and two isolated, self-healing errors. Must NOT raise an incident.

- **Expected:** False-positive guard: warning text mentions pools, timeouts, memory and rate limits but must not produce hypotheses.
- **Required hypotheses:** none
- **Forbidden hypotheses:** db_pool_exhaustion, network_timeout, memory_exhaustion, auth_failure, dependency_failure, rate_limiting, http_5xx
- **Required affected services:** none
- **Observed:** verdict `no_incident`, severity `none`, hypotheses none

## Rate limiting storm (`rate-limit-storm`)

A partner API throttles partner-sync with HTTP 429, which spills into billing.

- **Expected:** 429 / retry-after evidence ranks first.
- **Required hypotheses:** rate_limiting
- **Forbidden hypotheses:** memory_exhaustion, auth_failure, db_pool_exhaustion
- **Required affected services:** partner-sync, billing-api
- **Observed:** verdict `incident_detected`, severity `medium`, hypotheses rate_limiting (85.7)
