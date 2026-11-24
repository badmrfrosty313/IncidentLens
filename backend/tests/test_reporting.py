import json

from app.demo import run_scenario
from app.pipeline import analyze_text
from app.reporting import md_code, md_text, render_json, render_markdown


def test_markdown_report_contains_required_sections():
    md = render_markdown(run_scenario("db-pool-exhaustion").analysis)
    for heading in ("# IncidentLens incident report", "## Summary", "## Timeline", "## Root-cause hypotheses",
                    "### 1. Database connection pool exhaustion", "Supporting evidence:", "Recommended diagnostic actions:",
                    "## Recommended investigation steps", "## Data handling"):
        assert heading in md, heading
    assert "not statistical probabilities" in md
    assert "Error spike" in md


def test_markdown_for_cascade_lists_steps():
    md = render_markdown(run_scenario("cascading-microservice-failure").analysis)
    assert "Cascade" in md and "`inventory-db` began failing" in md


def test_markdown_for_healthy_system_has_no_hypotheses():
    md = render_markdown(run_scenario("healthy-system").analysis)
    assert "no incident" in md and "No hypotheses met the evidence threshold" in md


def test_json_report_is_valid_and_complete():
    r = run_scenario("memory-exhaustion").analysis
    data = json.loads(render_json(r))
    assert data["verdict"] == "incident_detected"
    assert data["hypotheses"][0]["category"] == "memory_exhaustion"
    assert data["hypotheses"][0]["evidence"] and data["hypotheses"][0]["recommended_actions"]
    assert "events" not in data and data["summary"]["total_events"] == r.summary.total_events
    assert "not statistical probabilities" in data["score_note"]


def test_markdown_neutralizes_hostile_log_content():
    hostile = "# Heading\n[click](javascript:alert(1)) <script>alert(1)</script> | a | b |\n![x](http://evil/x.png) `code`"
    text = "".join(f"2025-03-14T09:00:0{i}Z ERROR [a] authentication failed {hostile}\n" for i in range(6))
    md = render_markdown(analyze_text(text))
    assert "<script>" not in md
    assert "](javascript:" not in md and "![x](" not in md
    assert "\n# Heading" not in md  # no injected top-level heading


def test_helpers():
    assert md_text("a|b`c<d>") == "a\\|b'c&lt;d&gt;"
    assert md_code("x`y") == "`x'y`"
    assert md_text("x" * 500, 50).endswith("…") and len(md_text("x" * 500, 50)) <= 50
