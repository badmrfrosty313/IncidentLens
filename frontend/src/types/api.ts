/** Mirrors backend/app/models.py. Timestamps are ISO-8601 strings. */

export type Severity = "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export const SEVERITIES: readonly Severity[] = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] as const;

export type LogFormat = "plaintext" | "json" | "jsonl";
export type FormatHint = "auto" | LogFormat;
export type Verdict = "incident_detected" | "no_incident" | "insufficient_evidence";
export type IncidentSeverity = "none" | "low" | "medium" | "high" | "critical";
export type EvidenceLevel = "strong" | "moderate" | "weak";
export type HypothesisCategory =
  | "db_pool_exhaustion"
  | "network_timeout"
  | "memory_exhaustion"
  | "auth_failure"
  | "dependency_failure"
  | "rate_limiting"
  | "http_5xx";

export interface MalformedRecord { line_number: number; reason: string; sample: string }

export interface LogEvent {
  id: number;
  line_number: number;
  timestamp: string | null;
  severity: Severity;
  service: string;
  message: string;
}

export interface IngestStats {
  detected_format: LogFormat;
  input_bytes: number;
  total_records: number;
  parsed_records: number;
  malformed_records: number;
  malformed_samples: MalformedRecord[];
  events_without_timestamp: number;
  events_without_severity: number;
  events_with_naive_timestamp: number;
  truncated_messages: number;
  redactions: Record<string, number>;
  warnings: string[];
}

export interface ServiceSummary { name: string; events: number; errors: number; warnings: number }
export interface TimeRange { start: string | null; end: string | null; duration_seconds: number }

export interface Summary {
  total_events: number;
  error_count: number;
  critical_count: number;
  warning_count: number;
  error_ratio: number;
  severity_distribution: Record<Severity, number>;
  services: ServiceSummary[];
  affected_services: string[];
  time_range: TimeRange;
  incident_severity: IncidentSeverity;
  incident_severity_reasons: string[];
}

export interface ErrorGroup {
  signature: string;
  severity: Severity;
  count: number;
  services: string[];
  first_seen: string | null;
  last_seen: string | null;
  example: string;
}

export interface ExceptionPattern { name: string; count: number; services: string[]; buckets_present: number; recurring: boolean }
export interface TimelineBucket { start: string; end: string; counts: Record<Severity, number>; total: number }

export interface Spike {
  start: string;
  end: string;
  peak_count: number;
  total_errors: number;
  baseline: number;
  threshold: number;
  services: string[];
}

export interface CascadeStep { service: string; onset: string; offset_seconds: number; error_count: number; wave: number }
export interface CascadeFinding { origin_services: string[]; steps: CascadeStep[]; span_seconds: number; note: string }
export interface CorrelationPair { service_a: string; service_b: string; correlation: number; lag_seconds: number; interpretation: string }

export interface EvidenceItem {
  event_id: number;
  timestamp: string | null;
  service: string;
  severity: Severity;
  message: string;
  indicator: string;
}

export interface IndicatorHit { name: string; label: string; count: number }
export interface ScoreComponent { factor: string; points: number; max_points: number; detail: string }
export interface AffectedService { name: string; matched_events: number }

export interface Hypothesis {
  rank: number;
  category: HypothesisCategory;
  title: string;
  evidence_score: number;
  evidence_level: EvidenceLevel;
  summary: string;
  matched_events: number;
  first_seen: string | null;
  last_seen: string | null;
  affected_services: AffectedService[];
  indicators: IndicatorHit[];
  evidence: EvidenceItem[];
  score_breakdown: ScoreComponent[];
  recommended_actions: string[];
}

export interface RecommendedStep { priority: number; text: string; source: string }

export interface AnalysisResponse {
  engine: string;
  engine_version: string;
  verdict: Verdict;
  verdict_reason: string;
  score_note: string;
  summary: Summary;
  ingest: IngestStats;
  groups: ErrorGroup[];
  exception_patterns: ExceptionPattern[];
  timeline: TimelineBucket[];
  bucket_seconds: number;
  spikes: Spike[];
  cascade: CascadeFinding | null;
  correlations: CorrelationPair[];
  hypotheses: Hypothesis[];
  recommended_steps: RecommendedStep[];
  events: LogEvent[];
  events_total: number;
  events_truncated: boolean;
}

export interface ExpectedOutcome {
  verdict: Verdict;
  min_incident_severity: IncidentSeverity;
  max_incident_severity: IncidentSeverity;
  top_hypothesis: HypothesisCategory | null;
  required_hypotheses: HypothesisCategory[];
  forbidden_hypotheses: HypothesisCategory[];
  expect_spike: boolean;
  expect_cascade: boolean;
  required_affected_services: string[];
  description: string;
}

export interface ScenarioInfo { id: string; name: string; description: string; format: LogFormat; expected: ExpectedOutcome }
export interface DemoResponse { scenario: ScenarioInfo; analysis: AnalysisResponse }

/** What produced the current analysis; used to request matching report exports. */
export type AnalysisSource =
  | { kind: "demo"; scenarioId: string }
  | { kind: "content"; content: string; format: FormatHint; label: string };

export type ReportFormat = "markdown" | "json";
