import type { AnalysisResponse, LogEvent, ScenarioInfo, Severity } from "../types/api";

const T0 = Date.parse("2025-03-14T09:00:00Z");
export const iso = (offsetSeconds: number): string => new Date(T0 + offsetSeconds * 1000).toISOString();

export function makeEvent(id: number, offset: number, severity: Severity, service: string, message: string): LogEvent {
  return { id, line_number: id + 1, timestamp: iso(offset), severity, service, message };
}

export const EVENTS: LogEvent[] = [
  makeEvent(0, 0, "INFO", "api-gateway", "GET /api/v1/orders 200 12ms"),
  makeEvent(1, 10, "WARNING", "orders-api", "Connection pool utilization 85%"),
  makeEvent(2, 20, "ERROR", "orders-api", "TimeoutError: unable to acquire connection from pool"),
  makeEvent(3, 30, "ERROR", "api-gateway", "upstream orders-api returned status=500"),
  makeEvent(4, 40, "CRITICAL", "orders-db-proxy", "FATAL: remaining connection slots are reserved"),
  makeEvent(5, 50, "INFO", "billing-api", "GET /healthz 200 3ms"),
];

export const SCENARIO: ScenarioInfo = {
  id: "db-pool-exhaustion",
  name: "Database connection pool exhaustion",
  description: "orders-api runs out of database connections.",
  format: "plaintext",
  expected: {
    verdict: "incident_detected",
    min_incident_severity: "high",
    max_incident_severity: "high",
    top_hypothesis: "db_pool_exhaustion",
    required_hypotheses: ["db_pool_exhaustion"],
    forbidden_hypotheses: ["memory_exhaustion"],
    expect_spike: true,
    expect_cascade: false,
    required_affected_services: ["orders-api"],
    description: "Pool-exhaustion errors rank first.",
  },
};

export function makeAnalysis(overrides: Partial<AnalysisResponse> = {}): AnalysisResponse {
  return {
    engine: "deterministic-heuristics",
    engine_version: "0.1.0",
    verdict: "incident_detected",
    verdict_reason: "2 hypothesis(es) ranked by heuristic evidence score.",
    score_note: "Evidence scores are transparent heuristic ranking scores (0-100). They are not statistical probabilities.",
    summary: {
      total_events: 6,
      error_count: 3,
      critical_count: 1,
      warning_count: 1,
      error_ratio: 0.5,
      severity_distribution: { DEBUG: 0, INFO: 2, WARNING: 1, ERROR: 2, CRITICAL: 1 },
      services: [
        { name: "orders-api", events: 2, errors: 1, warnings: 1 },
        { name: "api-gateway", events: 2, errors: 1, warnings: 0 },
      ],
      affected_services: ["orders-api", "api-gateway", "orders-db-proxy"],
      time_range: { start: iso(0), end: iso(50), duration_seconds: 50 },
      incident_severity: "high",
      incident_severity_reasons: ["3 error event(s) (50.0% of 6 events)."],
    },
    ingest: {
      detected_format: "plaintext", input_bytes: 500, total_records: 6, parsed_records: 6, malformed_records: 0,
      malformed_samples: [], events_without_timestamp: 0, events_without_severity: 0, events_with_naive_timestamp: 0,
      truncated_messages: 0, redactions: { email: 2 }, warnings: [],
    },
    groups: [
      { signature: "TimeoutError: unable to acquire connection from pool", severity: "ERROR", count: 4, services: ["orders-api"], first_seen: iso(20), last_seen: iso(40), example: "TimeoutError" },
    ],
    exception_patterns: [{ name: "TimeoutError", count: 4, services: ["orders-api"], buckets_present: 4, recurring: true }],
    timeline: [0, 1, 2].map((i) => ({
      start: iso(i * 20), end: iso(i * 20 + 20),
      counts: { DEBUG: 0, INFO: 1, WARNING: i === 0 ? 1 : 0, ERROR: i === 1 ? 2 : 0, CRITICAL: i === 2 ? 1 : 0 },
      total: 2,
    })),
    bucket_seconds: 20,
    spikes: [{ start: iso(20), end: iso(40), peak_count: 2, total_errors: 2, baseline: 0, threshold: 5, services: ["orders-api"] }],
    cascade: null,
    correlations: [],
    hypotheses: [
      {
        rank: 1, category: "db_pool_exhaustion", title: "Database connection pool exhaustion", evidence_score: 84.2,
        evidence_level: "strong", summary: "12 event(s) across 2 service(s) matched connection-pool exhaustion.",
        matched_events: 12, first_seen: iso(10), last_seen: iso(40),
        affected_services: [{ name: "orders-api", matched_events: 10 }],
        indicators: [{ name: "cannot_acquire_connection", label: "Cannot acquire a connection", count: 10 }],
        evidence: [{ event_id: 2, timestamp: iso(20), service: "orders-api", severity: "ERROR", message: "TimeoutError: unable to acquire connection from pool", indicator: "Cannot acquire a connection" }],
        score_breakdown: [{ factor: "Matching volume", points: 25, max_points: 25, detail: "12 matching event(s)" }],
        recommended_actions: ["Compare pool size, in-use and waiting counts."],
      },
      {
        rank: 2, category: "http_5xx", title: "Elevated HTTP 5xx errors (symptom)", evidence_score: 40,
        evidence_level: "weak", summary: "5 events matched HTTP 5xx server errors.",
        matched_events: 5, first_seen: iso(30), last_seen: iso(40),
        affected_services: [{ name: "api-gateway", matched_events: 5 }], indicators: [],
        evidence: [], score_breakdown: [], recommended_actions: ["Treat 5xx as a symptom."],
      },
    ],
    recommended_steps: [{ priority: 1, text: "Start with the first error spike.", source: "spike" }],
    events: EVENTS,
    events_total: 6,
    events_truncated: false,
    ...overrides,
  };
}
