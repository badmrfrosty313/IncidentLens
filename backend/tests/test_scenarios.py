"""Automated evaluation of every demo scenario against its documented expected outcome."""

import pytest

from app.demo import SCENARIOS, evaluate, get_scenario, list_scenarios, run_scenario
from app.errors import UnknownScenarioError
from app.pipeline import analyze_text


def test_at_least_six_scenarios_including_required_ones():
    ids = {s.id for s in SCENARIOS}
    assert len(ids) >= 6
    assert {"db-pool-exhaustion", "memory-exhaustion", "auth-service-failure",
            "network-dependency-timeout", "cascading-microservice-failure", "healthy-system"} <= ids


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_scenario_matches_expected_outcome(scenario):
    result = run_scenario(scenario.id).analysis
    failures = evaluate(scenario.expected, result)
    assert not failures, failures


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_scenarios_are_deterministic(scenario):
    assert scenario.render() == scenario.render()
    a = analyze_text(scenario.render()).model_dump_json()
    b = analyze_text(scenario.render()).model_dump_json()
    assert a == b


def test_scenarios_cover_all_three_input_formats():
    assert {s.format for s in SCENARIOS} == {"plaintext", "json", "jsonl"}
    for s in SCENARIOS:
        assert analyze_text(s.render()).ingest.detected_format == s.format


def test_healthy_system_has_no_false_positive_even_with_scary_warning_text():
    sc = get_scenario("healthy-system")
    result = run_scenario(sc.id).analysis
    assert result.hypotheses == [] and result.spikes == [] and result.cascade is None
    assert result.summary.incident_severity == "none"
    assert result.summary.warning_count > 20  # warnings exist and mention pools/timeouts/limits
    assert result.recommended_steps == []


def test_a_handful_of_unrelated_errors_gives_insufficient_evidence_not_a_guess():
    lines = [f"2025-03-14T09:{m:02d}:00Z INFO [a] ok" for m in range(30)]
    lines += [f"2025-03-14T09:{m:02d}:30Z ERROR [a] weird thing {m} happened" for m in range(0, 30, 3)]
    result = analyze_text("\n".join(lines))
    assert result.verdict in {"insufficient_evidence", "no_incident"}
    assert result.hypotheses == []


def test_too_little_data_is_insufficient_evidence():
    r = analyze_text("2025-03-14T09:00:00Z ERROR [a] authentication failed\n")
    assert r.verdict == "insufficient_evidence" and r.hypotheses == []


def test_cascade_scenario_reports_origin_and_order():
    r = run_scenario("cascading-microservice-failure").analysis
    assert r.cascade and r.cascade.origin_services == ["inventory-db"]
    order = [s.service for s in r.cascade.steps]
    assert order == ["inventory-db", "inventory-service", "catalog-service", "search-api", "api-gateway", "web-frontend"]


def test_redaction_happens_in_auth_scenario():
    r = run_scenario("auth-service-failure").analysis
    blob = r.model_dump_json()
    for secret in ("alice@example.com", "bob.smith@example.org", "hunter2", "eyJhbGciOiJIUzI1NiJ9"):
        assert secret not in blob
    assert r.ingest.redactions.get("email", 0) > 0


def test_unknown_scenario():
    with pytest.raises(UnknownScenarioError):
        run_scenario("nope")
    assert len(list_scenarios()) == len(SCENARIOS)
