"""Demo scenarios, expected outcomes, and the evaluation helper."""

from __future__ import annotations

from ..config import DEFAULT_LIMITS, Limits
from ..errors import UnknownScenarioError
from ..models import AnalysisResponse, DemoResponse, ExpectedOutcome, ScenarioInfo
from ..pipeline import analyze_text
from .scenarios import SCENARIOS, Scenario, get_scenario

_SEV = ["none", "low", "medium", "high", "critical"]


def list_scenarios() -> list[ScenarioInfo]:
    return [s.info() for s in SCENARIOS]


def run_scenario(scenario_id: str, limits: Limits = DEFAULT_LIMITS) -> DemoResponse:
    sc = get_scenario(scenario_id)
    if sc is None:
        raise UnknownScenarioError(f"Unknown scenario: {scenario_id!r}")
    return DemoResponse(scenario=sc.info(), analysis=analyze_text(sc.render(), limits=limits))


def evaluate(expected: ExpectedOutcome, result: AnalysisResponse) -> list[str]:
    """Return a list of human-readable failures (empty list means the outcome matched)."""
    fails: list[str] = []
    cats = [h.category for h in result.hypotheses]
    sev = result.summary.incident_severity
    if result.verdict != expected.verdict:
        fails.append(f"verdict {result.verdict!r} != expected {expected.verdict!r}")
    if _SEV.index(sev) < _SEV.index(expected.min_incident_severity):
        fails.append(f"incident severity {sev!r} below minimum {expected.min_incident_severity!r}")
    if _SEV.index(sev) > _SEV.index(expected.max_incident_severity):
        fails.append(f"incident severity {sev!r} above maximum {expected.max_incident_severity!r}")
    if expected.top_hypothesis and (not cats or cats[0] != expected.top_hypothesis):
        fails.append(f"top hypothesis {cats[:1]} != expected {expected.top_hypothesis!r}")
    fails += [f"missing required hypothesis {c!r}" for c in expected.required_hypotheses if c not in cats]
    fails += [f"forbidden hypothesis {c!r} was produced" for c in expected.forbidden_hypotheses if c in cats]
    if bool(result.spikes) != expected.expect_spike:
        fails.append(f"spike detected={bool(result.spikes)} != expected {expected.expect_spike}")
    if (result.cascade is not None) != expected.expect_cascade:
        fails.append(f"cascade detected={result.cascade is not None} != expected {expected.expect_cascade}")
    affected = set(result.summary.affected_services)
    fails += [f"service {s!r} not reported as affected" for s in expected.required_affected_services if s not in affected]
    return fails


__all__ = ["SCENARIOS", "Scenario", "get_scenario", "list_scenarios", "run_scenario", "evaluate"]
