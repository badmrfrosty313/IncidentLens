import type { AnalysisResponse, ExpectedOutcome, IncidentSeverity } from "../types/api";

const ORDER: IncidentSeverity[] = ["none", "low", "medium", "high", "critical"];

/**
 * Compare an analysis with a demo scenario's documented expected outcome.
 * Mirrors backend/app/demo/__init__.py::evaluate. Returns human-readable mismatches.
 */
export function checkExpected(expected: ExpectedOutcome, a: AnalysisResponse): string[] {
  const out: string[] = [];
  const cats = a.hypotheses.map((h) => h.category);
  const sev = ORDER.indexOf(a.summary.incident_severity);
  if (a.verdict !== expected.verdict) out.push(`verdict is ${a.verdict}, expected ${expected.verdict}`);
  if (sev < ORDER.indexOf(expected.min_incident_severity)) out.push(`severity below ${expected.min_incident_severity}`);
  if (sev > ORDER.indexOf(expected.max_incident_severity)) out.push(`severity above ${expected.max_incident_severity}`);
  if (expected.top_hypothesis && cats[0] !== expected.top_hypothesis) out.push(`top hypothesis is ${cats[0] ?? "none"}, expected ${expected.top_hypothesis}`);
  for (const c of expected.required_hypotheses) if (!cats.includes(c)) out.push(`missing hypothesis ${c}`);
  for (const c of expected.forbidden_hypotheses) if (cats.includes(c)) out.push(`unexpected hypothesis ${c}`);
  if ((a.spikes.length > 0) !== expected.expect_spike) out.push(`spike detected = ${a.spikes.length > 0}, expected ${expected.expect_spike}`);
  if ((a.cascade !== null) !== expected.expect_cascade) out.push(`cascade detected = ${a.cascade !== null}, expected ${expected.expect_cascade}`);
  for (const s of expected.required_affected_services) if (!a.summary.affected_services.includes(s)) out.push(`service ${s} not affected`);
  return out;
}
