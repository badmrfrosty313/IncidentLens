# Architecture

## Principles

1. **Deterministic and explainable.** Every hypothesis is traceable to matched log lines and a published score formula.
2. **Stages are separate and HTTP-free.** The analysis core never imports FastAPI; the API layer only validates and maps errors.
3. **Redact first.** Parsing extracts fields; redaction runs immediately after, before anything is normalized, analyzed, returned or reported.
4. **No infrastructure.** No database, auth system, queue or external service. All processing is in memory for the duration of one request.
5. **Honest uncertainty.** Heuristic scores are not probabilities; "insufficient evidence" and "no incident" are first-class outcomes.

## Pipeline

```
raw text ──► parsing ──► redaction ──► normalization ──► analysis ──► AnalysisResponse ──► reporting (MD / JSON)
            parsing.py   redaction.py  normalization.py  analysis/     models.py           reporting.py
                                                         ├ grouping.py      (signatures, exception patterns)
                                                         ├ timeline.py      (buckets, spike detection)
                                                         ├ correlation.py   (onsets, cascade, lagged correlation)
                                                         ├ hypotheses.py    (rules + scoring)
                                                         └ engine.py        (orchestration, severity, verdict, steps)
pipeline.py composes the stages (analyze_text). main.py exposes them over HTTP.
```

| Module | Responsibility |
| --- | --- |
| `config.py` | `Limits` dataclass; env overrides |
| `errors.py` | Domain errors with HTTP status hints (`413`, `422`, `404`) |
| `models.py` | Pydantic contracts shared by the engine, reports and API (mirrored by `frontend/src/types/api.ts`) |
| `parsing.py` | Format detection; plaintext, JSONL, JSON parsers → `RawRecord`s + malformed list; early record-count rejection |
| `redaction.py` | Ordered, bounded regex rules with cheap pre-checks; per-category counts |
| `normalization.py` | Timestamp / severity / service / message normalization; time-ordered `LogEvent`s |
| `analysis/*` | Deterministic analysis stages (below) |
| `reporting.py` | Markdown / JSON rendering; neutralizes untrusted text |
| `llm.py` | `HypothesisEnricher` protocol + `NullEnricher`; the only future-LLM seam (not used in the MVP) |
| `demo/` | Seeded scenario generators, expected outcomes, `evaluate()` |
| `middleware.py` | Pure-ASGI request-body size guard |

## Analysis details

**Timeline.** Events are bucketed into ≈60 buckets by choosing the smallest size from a fixed ladder (1 s … 1 d). Buckets are contiguous (zeros included).

**Spikes.** `baseline` = median of the quietest half of buckets' ERROR+CRITICAL counts; `threshold = max(baseline + 3·max(√baseline, 1), 5)`.
Buckets ≥ threshold form a spike (runs merged across a single quiet bucket). Using the quiet half keeps long incidents detectable. Fewer than 8 buckets → no spike claim.

**Cascade.** A service's *onset* is the first error that begins a burst of ≥ 3 errors within `max(60 s, 5 buckets)` (so a stray early error cannot become the "origin").
Onsets are clustered into *waves* (an onset within one bucket of its wave's first onset joins that wave). A cascade requires **≥ 3 waves** with gaps ≤ `max(120 s, 25 % of the window)`. The output is an ordered list; it is an investigation lead, not proof of causality.

**Correlation.** Pearson *r* of per-service error-count series (top 8 services), best lag in ±3 buckets, reported when r ≥ 0.6.

**Grouping.** Signatures replace UUIDs, hex ids, IPs and numbers with placeholders (keeping 4xx/5xx codes) so near-identical messages group.

**Hypotheses.** Only WARNING+ events are considered. Each rule has named indicators (regexes and/or HTTP status sets). More specific rules claim events first
(timeouts that mention a connection *pool* count toward pool exhaustion, not network timeouts). A hypothesis is emitted only with ≥ 3 matching events including ≥ 2 ERROR+ and score ≥ 25.

Evidence score (0–100, a ranking aid):

| Component | Max | Rule |
| --- | ---: | --- |
| Matching volume | 25 | `min(1, n/10)·25` |
| Indicator diversity | 15 | `min(2, distinct)/2·15` |
| Severity | 15 | share of matches that are ERROR/CRITICAL · 15 |
| Coincides with error spike | 20 | share of matches inside a detected spike · 20 (0 if no spike) |
| Share of all errors | 15 | `min(1, n_err/total_errors)·15` |
| Early-warning precursors | 10 | 10 if matching WARNINGs precede the first matching error |

Levels: `strong` ≥ 65, `moderate` ≥ 45, otherwise `weak`. The breakdown is returned with every hypothesis and rendered in the UI and reports.

**Incident severity** (max of triggered rules, all listed as reasons): `none` if no errors, or < 1 % errors with no spike/cascade/CRITICAL; `low` otherwise;
`medium` for a spike or ≥ 5 % errors; `high` for ≥ 15 % errors or CRITICAL during a spike; `critical` for a cascade or ≥ 30 % errors.

**Verdict.** `no_incident` when severity is `none` (hypotheses are suppressed, the main false-positive guard); `insufficient_evidence` when there are < 5 events or errors exist but no rule has enough evidence; otherwise `incident_detected`.

## Frontend

React + TypeScript (strict) + Vite + Tailwind (dark only) + Recharts.

```
src/types/api.ts      typed mirror of the API models
src/lib/              api client, filtering, formatting, downloads, expected-outcome check (framework-free, unit-tested)
src/components/       Header, IngestPanel, StatCards, TimelineChart, SeverityChart, ErrorFrequencyChart,
                      HypothesisList, FindingsPanel, InvestigationSteps, LogViewer, ExportButtons, ExpectedOutcomeCard
src/App.tsx           state (analysis, source, time-window filter), stale-request guard
```

Log text is only ever rendered as React text nodes (no `dangerouslySetInnerHTML`). Clicking a timeline bar sets a time-window filter on the log viewer.

## Extension point for an optional LLM

`llm.HypothesisEnricher.enrich(response) -> response` receives the *structured, already-redacted* `AnalysisResponse`, never raw input, and must not mutate it.
`analyze_text(..., enricher=…)` applies it after the deterministic analysis, so the deterministic hypotheses remain the source of truth and the MVP works with no keys.
