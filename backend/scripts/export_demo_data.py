#!/usr/bin/env python3
"""Write the synthetic demo datasets to data/demo/ and regenerate docs/DEMO_SCENARIOS.md.

    python scripts/export_demo_data.py

The files are byte-for-byte what the API serves (seeded generators), so they can be uploaded
through the UI or POSTed to /api/analyze. A test asserts the committed files stay in sync.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

from app.demo import SCENARIOS, run_scenario  # noqa: E402


def main() -> None:
    out = REPO / "data" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for sc in SCENARIOS:
        (out / f"{sc.id}.{sc.extension}").write_text(sc.render(), encoding="utf-8", newline="\n")
        a = run_scenario(sc.id).analysis
        e = sc.expected
        rows.append((sc, e, a))

    lines = [
        "# Demo scenarios and expected outcomes",
        "",
        "All data is **synthetic** and deterministic (seeded generators in `backend/app/demo/scenarios.py`). Datasets are also",
        "exported to `data/demo/` by `python backend/scripts/export_demo_data.py` and can be uploaded through the UI.",
        "Some messages intentionally contain fake emails, passwords and tokens to exercise redaction.",
        "",
        "The expected outcomes below are machine-checked by `backend/tests/test_scenarios.py` and",
        "`python backend/scripts/evaluate_demos.py`. The observed numbers are from the current engine.",
        "",
        "| Scenario | Format | Events | Expected verdict | Expected severity | Expected top hypothesis | Spike | Cascade |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for sc, e, a in rows:
        sev = e.min_incident_severity if e.min_incident_severity == e.max_incident_severity else f">= {e.min_incident_severity}"
        lines.append(
            f"| `{sc.id}` | {sc.format} | {a.summary.total_events:,} | {e.verdict.replace('_', ' ')} | {sev} | "
            f"{e.top_hypothesis or 'none'} | {'yes' if e.expect_spike else 'no'} | {'yes' if e.expect_cascade else 'no'} |"
        )
    for sc, e, a in rows:
        lines += [
            "",
            f"## {sc.name} (`{sc.id}`)",
            "",
            sc.description,
            "",
            f"- **Expected:** {e.description}",
            f"- **Required hypotheses:** {', '.join(e.required_hypotheses) or 'none'}",
            f"- **Forbidden hypotheses:** {', '.join(e.forbidden_hypotheses) or 'none'}",
            f"- **Required affected services:** {', '.join(e.required_affected_services) or 'none'}",
            f"- **Observed:** verdict `{a.verdict}`, severity `{a.summary.incident_severity}`, hypotheses "
            + (", ".join(f"{h.category} ({h.evidence_score:.1f})" for h in a.hypotheses) or "none"),
        ]
    (REPO / "docs").mkdir(exist_ok=True)
    (REPO / "docs" / "DEMO_SCENARIOS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} datasets to {out} and docs/DEMO_SCENARIOS.md")


if __name__ == "__main__":
    main()
