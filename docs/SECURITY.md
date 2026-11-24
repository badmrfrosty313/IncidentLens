# Security notes

## Threat model

All uploaded content is **untrusted data**. The service is intended for local or internal use; it has no authentication (by design for the MVP) and must not be exposed to the public internet as-is.

| Threat | Mitigation |
| --- | --- |
| Secrets in logs leaking into responses, reports or exports | Redaction runs before normalization/analysis; messages, service names and malformed-record samples are all redacted; an end-to-end test asserts planted secrets never appear in the response, Markdown or JSON report. |
| Raw log retention / exfiltration | No persistence layer; no disk writes or network calls during analysis (a test fails if either is attempted); no external LLM calls. |
| Memory / CPU exhaustion via large input | Body-size middleware (413 before buffering, also for chunked bodies), decoded-size limit, record-count limit (rejected, not truncated), line-length cap, continuation-line cap, 5,000-event response cap. |
| Regex DoS in redaction / parsing | Bounded quantifiers, anchored patterns, lookbehind on the email rule, cheap substring pre-checks; adversarial-input tests assert sub-second runtime. |
| JSON bombs / deep nesting | `RecursionError`/`ValueError` from the JSON parser are caught per record and counted as malformed. |
| Markdown / HTML injection through log text | Report renderer escapes `\ ` | < > [ ] * _ # !`, strips control characters and puts messages in code spans; frontend renders text nodes only. Tests cover hostile content. |
| Path traversal via filenames | Server never touches filesystems; exported filenames are sanitized client-side to `[a-z0-9._-]`. |
| Container hardening | Non-root users, read-only filesystems, dropped capabilities, `no-new-privileges`, CSP and other headers on nginx. |

## What redaction covers

API keys with well-known prefixes (OpenAI-style `sk-`, Stripe, AWS `AKIA`/`ASIA`, GitHub, Slack, Google, GitLab, npm), `key=value` / JSON assignments whose key contains
password / passwd / pwd / secret / token / api-key / access-key / credential, `Authorization` headers (incl. Basic/Bearer/Digest), bare `Bearer` tokens, JWTs, credentials inside URLs
(`scheme://user:pass@host`), emails, PEM private keys.

## Known gaps (see also LIMITATIONS.md)

- Pattern-based: secrets without a recognizable prefix or key name (free-text "the password is hunter2", bare high-entropy strings, card numbers, SSNs, IPs, names) are **not** detected.
- The secret-assignment rule is intentionally broad (`max_tokens=100` is redacted) — it errs toward over-redaction.
- JSON parsing necessarily happens before redaction; parsed fields live in memory only for the duration of the request.
- No rate limiting, authentication or TLS in the app itself; put it behind a reverse proxy / VPN for shared deployments.
- Reports and exports should be reviewed before sharing.

## Files that deserve independent security review

1. `backend/app/redaction.py` — rule coverage, ordering, backtracking behaviour.
2. `backend/app/parsing.py` — untrusted-input parsing, limits, clipping near secrets.
3. `backend/app/middleware.py` and `backend/app/main.py` — request limits, CORS, error handling.
4. `backend/app/reporting.py` — output neutralization.
5. `frontend/src/components/LogViewer.tsx`, `HypothesisList.tsx`, `IngestPanel.tsx` — rendering/ingesting untrusted text and files.
6. `frontend/nginx.conf`, `docker-compose.yml`, Dockerfiles — deployment hardening.
