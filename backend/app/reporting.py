"""Incident report rendering (Markdown and JSON).

Log content is untrusted. In Markdown every log-derived string is neutralized so it cannot
inject headings, links, HTML or table structure into the report.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from .models import SCORE_NOTE, AnalysisResponse

_CTRL = re.compile(r"[\x00-\x1f\x7f]+")


def md_text(value: object, limit: int = 200) -> str:
    """Make arbitrary text safe for inline Markdown / table cells."""
    s = _CTRL.sub(" ", str(value)).strip()
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    for ch, rep in (("\\", "\\\\"), ("`", "'"), ("|", "\\|"), ("<", "&lt;"), (">", "&gt;"),
                    ("[", "\\["), ("]", "\\]"), ("*", "\\*"), ("_", "\\_"), ("#", "\\#"), ("!", "\\!")):
        s = s.replace(ch, rep)
    return s


def md_code(value: object, limit: int = 200, *, cell: bool = False) -> str:
    """Inline code span. Pass ``cell=True`` inside a table row: GFM splits cells on every ``|``,
    even within a code span, unless it is escaped as ``\\|``."""
    s = _CTRL.sub(" ", str(value)).strip().replace("`", "'")
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    if cell:
        s = s.replace("|", "\\|")
    return f"`{s}`" if s else "``"


def _t(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "n/a"


def _cell(value: object, limit: int = 120) -> str:
    return md_text(value, limit)


def render_markdown(r: AnalysisResponse) -> str:
    s = r.summary
    out: list[str] = ["# IncidentLens incident report", ""]
    out += [
        f"**Verdict:** {r.verdict.replace('_', ' ')}  ",
        f"**Incident severity:** {s.incident_severity}  ",
        f"**Analysis engine:** {r.engine} v{r.engine_version}",
        "",
        md_text(r.verdict_reason, 500),
        "",
        "## Summary",
        "",
        "| Metric | Value |", "| --- | --- |",
        f"| Events analyzed | {s.total_events:,} |",
        f"| Errors (ERROR + CRITICAL) | {s.error_count:,} |",
        f"| Critical | {s.critical_count:,} |",
        f"| Warnings | {s.warning_count:,} |",
        f"| Error ratio | {s.error_ratio:.2%} |",
        f"| Time range | {_t(s.time_range.start)} to {_t(s.time_range.end)} |",
        f"| Affected services | {_cell(', '.join(s.affected_services) or 'none')} |",
        f"| Input format | {r.ingest.detected_format} ({r.ingest.malformed_records} malformed record(s) skipped) |",
        "",
        "Severity rationale:",
        "",
        *[f"- {md_text(x, 300)}" for x in s.incident_severity_reasons],
        "",
        "## Timeline",
        "",
    ]
    notable = [b for b in r.timeline if b.counts["ERROR"] + b.counts["CRITICAL"] + b.counts["WARNING"] > 0]
    if r.spikes:
        for sp in r.spikes:
            out.append(
                f"- **Error spike** {_t(sp.start)} to {_t(sp.end)}: {sp.total_errors} errors, peak {sp.peak_count} per "
                f"{r.bucket_seconds}s bucket (baseline {sp.baseline}, threshold {sp.threshold}); services: "
                f"{_cell(', '.join(sp.services))}."
            )
    if r.cascade:
        out.append(f"- **Cascade** {md_text(r.cascade.note, 400)}")
        for st in r.cascade.steps:
            out.append(f"  - +{st.offset_seconds:.0f}s: {md_code(st.service)} began failing ({st.error_count} errors)")
    if not r.spikes and not r.cascade:
        out.append("- No error spike or cascade was detected.")
    if notable:
        out += ["", f"Bucket detail (bucket size {r.bucket_seconds}s, first {min(len(notable), 30)} buckets with warnings or errors):", "",
                "| Bucket start | Warn | Error | Critical |", "| --- | ---: | ---: | ---: |"]
        out += [f"| {_t(b.start)} | {b.counts['WARNING']} | {b.counts['ERROR']} | {b.counts['CRITICAL']} |" for b in notable[:30]]
    out += ["", "## Root-cause hypotheses", "", f"_{md_text(SCORE_NOTE, 400)}_", ""]
    if not r.hypotheses:
        out.append("No hypotheses met the evidence threshold (insufficient evidence or no incident).")
    for h in r.hypotheses:
        out += [
            f"### {h.rank}. {md_text(h.title)} (evidence score {h.evidence_score:.1f}/100, {h.evidence_level})",
            "",
            md_text(h.summary, 600),
            "",
            f"Affected services: {_cell(', '.join(f'{a.name} ({a.matched_events})' for a in h.affected_services))}",
            "",
            "Score breakdown:",
            "",
            "| Factor | Points | Detail |", "| --- | ---: | --- |",
            *[f"| {_cell(c.factor)} | {c.points:g}/{c.max_points:g} | {_cell(c.detail, 200)} |" for c in h.score_breakdown],
            "",
            "Supporting evidence:",
            "",
            *[f"- {_t(e.timestamp)} {md_code(e.service)} {e.severity.value}: {md_code(e.message, 240)}" for e in h.evidence],
            "",
            "Recommended diagnostic actions:",
            "",
            *[f"{i}. {md_text(a, 300)}" for i, a in enumerate(h.recommended_actions, 1)],
            "",
        ]
    out += ["## Recommended investigation steps", ""]
    out += [f"{st.priority}. {md_text(st.text, 400)}" for st in r.recommended_steps] or ["No investigation steps; no incident was detected."]
    out += ["", "## Most frequent warning/error patterns", "", "| Count | Severity | Services | Pattern |", "| ---: | --- | --- | --- |"]
    out += [f"| {g.count} | {g.severity.value} | {_cell(', '.join(g.services[:3]))} | {md_code(g.signature, 160, cell=True)} |" for g in r.groups[:10]]
    if r.correlations:
        out += ["", "## Temporal correlation", ""]
        out += [f"- {md_text(c.interpretation)} (r = {c.correlation:.2f})" for c in r.correlations[:5]]
    redactions = ", ".join(f"{k}: {v}" for k, v in r.ingest.redactions.items()) or "none"
    out += ["", "## Data handling", "",
            f"Sensitive values were redacted before analysis (counts: {md_text(redactions)}). Raw logs are not stored. "
            "Redaction is pattern-based and best-effort; review this report before sharing it.", ""]
    if r.ingest.warnings:
        out += ["Ingestion warnings:", "", *[f"- {md_text(w, 300)}" for w in r.ingest.warnings], ""]
    return "\n".join(out)


def render_json(r: AnalysisResponse) -> str:
    """Full structured report. The (potentially large) event list is omitted."""
    data = r.model_dump(mode="json", exclude={"events"})
    data["events_note"] = f"{r.events_total} normalized events analyzed; the event list is omitted from the JSON report."
    return json.dumps(data, indent=2, ensure_ascii=False)
