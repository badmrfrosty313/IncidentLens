# Security notes

## Threat model

All uploaded content is **untrusted data**. The service is intended for local or internal use; it has no authentication (by design for the MVP) and must not be exposed to the public internet as-is.

| Threat | Mitigation |
| --- | --- |
| Secrets in logs leaking into responses, reports or exports | Redaction runs before normalization/analysis; messages, service names and malformed-record samples are all redacted; end-to-end tests assert that the *planted, pattern-covered* secrets do not appear in the response, Markdown or JSON report. Redaction is best-effort: secrets with no recognizable shape are not detected (see Known gaps). |
| Raw log retention / exfiltration | No persistence layer; no disk writes or network calls during analysis (a test fails if either is attempted); no external LLM calls. |
| Memory / CPU exhaustion via large input | Body-size middleware (413 before buffering, also for chunked bodies), decoded-size limit, record-count limit (rejected, not truncated), line-length cap, continuation-line cap, 5,000-event response cap. |
| Secrets echoed back in error responses | FastAPI's default 422 body includes the submitted `input` (here: the raw upload). A custom handler returns only `{loc, type}` per error, never values, messages or context; regression tests post secrets in field values, wrongly typed fields, malformed JSON bodies and query parameters. |
| Secrets cut by length limits | Lines, JSON string fields and malformed-record samples are clipped *before* redaction (that bound keeps redaction cheap). Clipping drops the partial trailing token, so a half-visible key cannot survive; quoted `password="…` values with no closing quote are redacted to the end of the text. |
| Multi-line private keys | Key bodies are bare base64 lines that match no log shape. The plaintext parser swallows everything between `BEGIN … PRIVATE KEY` and `END` (or the next timestamped record; there is no line cap, so long keys cannot spill into malformed samples) so no body line is kept as a malformed sample; the header itself is redacted with the rest of its record. JSON strings carrying a key are covered by the multi-line redaction rule. |
| Malformed numeric fields | Severity values that are NaN, infinite, absurdly long, non-ASCII digits or out of range are treated as an unknown level; they cannot raise (previously a 500). |
| Memory exhaustion via many distinct services | Correlation counts errors per service first and allocates per-bucket arrays only for the top eight. |
| Oversized chunked uploads | The body-limit middleware does not raise from `receive()` (FastAPI would turn that into a 400); it reports a disconnect to the app and answers 413 itself. Tested at the ASGI level and against the real FastAPI stack. |
| Regex DoS in redaction / parsing | Bounded quantifiers, anchored patterns, lookbehind on the email rule, cheap substring pre-checks; adversarial-input tests assert sub-second runtime. |
| JSON bombs / deep nesting | `RecursionError`/`ValueError` from the JSON parser are caught per record and counted as malformed. |
| Markdown / HTML injection through log text | Report renderer escapes `\ ` | < > [ ] * _ # !`, strips control characters and puts messages in code spans; code spans inside table rows also escape `|` (GFM splits cells on pipes even inside code). Frontend renders text nodes only. Tests cover hostile content and table structure. |
| Path traversal via filenames | Server never touches filesystems; exported filenames are sanitized client-side to `[a-z0-9._-]`. |
| Container hardening | Non-root users, read-only filesystems, dropped capabilities, `no-new-privileges`, CSP and other headers on nginx. |

## What redaction covers

API keys with well-known prefixes (OpenAI-style `sk-`, Stripe, AWS `AKIA`/`ASIA`, GitHub, Slack, Google, GitLab, npm), `key=value` / JSON assignments whose key contains
password / passwd / pwd / secret / token / api-key / access-key / credential, `Authorization` headers (incl. Basic/Bearer/Digest), bare `Bearer` tokens, JWTs, credentials inside URLs
(`scheme://user:pass@host`), emails, PEM private keys.

## Known gaps (see also LIMITATIONS.md)

- Pattern-based: secrets without a recognizable prefix or key name (free-text "the password is hunter2", bare high-entropy strings, card numbers, SSNs, IPs, names) are **not** detected.
- The secret-assignment rule is intentionally broad (`max_tokens=100` is redacted) — it errs toward over-redaction.
- Quoted secret values handle single and double escaping (`"pa\"ss"`, and the `\\\"` form inside JSON-in-JSON), unterminated and malformed strings; deeper nesting levels (triple-encoded JSON) are not modelled and may leave a tail.
- Private-key handling is marker-based: it needs a `BEGIN … PRIVATE KEY` line. Bare base64 without a marker is not recognised, public keys and certificates are intentionally left alone, and an unterminated block discards following non-timestamped lines until the next timestamped record (a data-loss trade-off, reported as an ingest warning). Keys embedded in JSON strings rely on the multi-line redaction rule instead of the parser, and a key whose header was clipped away is not recognised.
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
