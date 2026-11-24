"""Typed data contracts shared by the pipeline, reporting and the HTTP layer."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


SEVERITY_RANK: dict[Severity, int] = {
    Severity.DEBUG: 0,
    Severity.INFO: 1,
    Severity.WARNING: 2,
    Severity.ERROR: 3,
    Severity.CRITICAL: 4,
}

LogFormat = Literal["plaintext", "json", "jsonl"]
Verdict = Literal["incident_detected", "no_incident", "insufficient_evidence"]
IncidentSeverity = Literal["none", "low", "medium", "high", "critical"]
EvidenceLevel = Literal["strong", "moderate", "weak"]
HypothesisCategory = Literal[
    "db_pool_exhaustion",
    "network_timeout",
    "memory_exhaustion",
    "auth_failure",
    "dependency_failure",
    "rate_limiting",
    "http_5xx",
]

SCORE_NOTE = (
    "Evidence scores are transparent heuristic ranking scores (0-100) built from the listed "
    "components. They are not statistical probabilities and do not measure confidence that a "
    "hypothesis is the true cause."
)


# ----------------------------------------------------------------------------- ingestion


class MalformedRecord(BaseModel):
    line_number: int
    reason: str
    sample: str


class LogEvent(BaseModel):
    id: int
    line_number: int
    timestamp: datetime | None
    severity: Severity
    service: str
    message: str


class IngestStats(BaseModel):
    detected_format: LogFormat
    input_bytes: int
    total_records: int
    parsed_records: int
    malformed_records: int
    malformed_samples: list[MalformedRecord] = Field(default_factory=list)
    events_without_timestamp: int = 0
    events_without_severity: int = 0
    events_with_naive_timestamp: int = 0
    truncated_messages: int = 0
    redactions: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------- analysis


class ServiceSummary(BaseModel):
    name: str
    events: int
    errors: int
    warnings: int


class TimeRange(BaseModel):
    start: datetime | None
    end: datetime | None
    duration_seconds: float


class Summary(BaseModel):
    total_events: int
    error_count: int  # ERROR + CRITICAL
    critical_count: int
    warning_count: int
    error_ratio: float
    severity_distribution: dict[str, int]
    services: list[ServiceSummary]
    affected_services: list[str]
    time_range: TimeRange
    incident_severity: IncidentSeverity
    incident_severity_reasons: list[str]


class ErrorGroup(BaseModel):
    signature: str
    severity: Severity
    count: int
    services: list[str]
    first_seen: datetime | None
    last_seen: datetime | None
    example: str


class ExceptionPattern(BaseModel):
    name: str
    count: int
    services: list[str]
    buckets_present: int
    recurring: bool


class TimelineBucket(BaseModel):
    start: datetime
    end: datetime
    counts: dict[str, int]
    total: int


class Spike(BaseModel):
    start: datetime
    end: datetime
    peak_count: int
    total_errors: int
    baseline: float
    threshold: float
    services: list[str]


class CascadeStep(BaseModel):
    service: str
    onset: datetime
    offset_seconds: float
    error_count: int
    wave: int


class CascadeFinding(BaseModel):
    origin_services: list[str]
    steps: list[CascadeStep]
    span_seconds: float
    note: str


class CorrelationPair(BaseModel):
    service_a: str
    service_b: str
    correlation: float
    lag_seconds: float
    interpretation: str


class EvidenceItem(BaseModel):
    event_id: int
    timestamp: datetime | None
    service: str
    severity: Severity
    message: str
    indicator: str


class IndicatorHit(BaseModel):
    name: str
    label: str
    count: int


class ScoreComponent(BaseModel):
    factor: str
    points: float
    max_points: float
    detail: str


class AffectedService(BaseModel):
    name: str
    matched_events: int


class Hypothesis(BaseModel):
    rank: int
    category: HypothesisCategory
    title: str
    evidence_score: float
    evidence_level: EvidenceLevel
    summary: str
    matched_events: int
    first_seen: datetime | None
    last_seen: datetime | None
    affected_services: list[AffectedService]
    indicators: list[IndicatorHit]
    evidence: list[EvidenceItem]
    score_breakdown: list[ScoreComponent]
    recommended_actions: list[str]


class RecommendedStep(BaseModel):
    priority: int
    text: str
    source: str


class AnalysisResponse(BaseModel):
    engine: str = "deterministic-heuristics"
    engine_version: str
    verdict: Verdict
    verdict_reason: str
    score_note: str = SCORE_NOTE
    summary: Summary
    ingest: IngestStats
    groups: list[ErrorGroup]
    exception_patterns: list[ExceptionPattern]
    timeline: list[TimelineBucket]
    bucket_seconds: int
    spikes: list[Spike]
    cascade: CascadeFinding | None
    correlations: list[CorrelationPair]
    hypotheses: list[Hypothesis]
    recommended_steps: list[RecommendedStep]
    events: list[LogEvent]
    events_total: int
    events_truncated: bool


# ----------------------------------------------------------------------------- HTTP


class AnalyzeRequest(BaseModel):
    content: str = Field(min_length=1, description="Raw log content (plaintext, JSON or JSONL).")
    format: Literal["auto", "plaintext", "json", "jsonl"] = "auto"


class ExpectedOutcome(BaseModel):
    verdict: Verdict
    min_incident_severity: IncidentSeverity
    max_incident_severity: IncidentSeverity = "critical"
    top_hypothesis: HypothesisCategory | None = None
    required_hypotheses: list[HypothesisCategory] = Field(default_factory=list)
    forbidden_hypotheses: list[HypothesisCategory] = Field(default_factory=list)
    expect_spike: bool
    expect_cascade: bool
    required_affected_services: list[str] = Field(default_factory=list)
    description: str


class ScenarioInfo(BaseModel):
    id: str
    name: str
    description: str
    format: LogFormat
    expected: ExpectedOutcome


class DemoResponse(BaseModel):
    scenario: ScenarioInfo
    analysis: AnalysisResponse
