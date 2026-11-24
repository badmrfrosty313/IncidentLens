# Known limitations

**Analysis**

- Hypotheses come from keyword/regex rules and a fixed score formula. Unusual wording, non-English logs, or custom error codes will not match; the engine then reports *insufficient evidence*.
- Evidence scores are ranking aids. They are **not** probabilities and the weights are heuristic, not fitted to data.
- Spike detection assumes timestamped events and at least 8 time buckets. Very short or undated logs get no spike/cascade/timeline analysis.
- Cascade and correlation findings show *ordering and co-movement* of errors; they do not prove causality. Clock skew between hosts can distort onset order.
- Severity thresholds (1 % / 5 % / 15 % / 30 %) are documented defaults, not tuned per system.
- Only WARNING-and-above events feed hypotheses; INFO-level evidence (for example, a latency regression) is ignored.
- Error-signature grouping is regex-based; messages with embedded free text may not collapse together.
- Demo scenarios are synthetic and authored alongside the rules, so passing them demonstrates behaviour, not real-world accuracy.

**Parsing**

- Plaintext support covers common `timestamp level [service] message` shapes; arbitrary free-form formats (syslog without year, multi-line JSON, logfmt) are not parsed and are counted as malformed.
- A service written as a bare lowercase word followed by `:` is read as the service name (`db: connection lost`); this can misread some messages.
- Records without a timestamp are kept and counted but excluded from time-based analysis. Timestamps without a timezone are treated as UTC.
- A single request is limited to 20 MiB / 100,000 records by default.

**Product / operations**

- No authentication, persistence, history, multi-user features or streaming ingestion; each analysis is stateless.
- The log viewer receives at most 5,000 events per analysis (warnings/errors first, INFO sampled). Totals and charts always cover every analyzed event.
- No license file is included: adding one needs the repository owner's decision (MIT was suggested but is not applied without explicit authorization).
- The Docker smoke test (`scripts/smoke.sh`) is HTTP-level; there is no real-browser (Playwright/Cypress) test, so chart rendering and interactions are covered only by Vitest/jsdom.
- Redaction is best-effort (see SECURITY.md).
- The static demonstration contains only the seven pre-computed synthetic scenarios; it cannot analyze other input.
- Six npm advisories remain in development tooling (Vitest/Vite); see "Dependency audit" in SECURITY.md.
- Browser coverage is Chromium (desktop and Pixel-7-sized viewports); Firefox and Safari are untested.

