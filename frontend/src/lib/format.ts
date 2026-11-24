import type { EvidenceLevel, IncidentSeverity, Severity, Verdict } from "../types/api";

const pad = (n: number): string => String(n).padStart(2, "0");

/** HH:MM:SS (UTC) for tables; the dashboard consistently shows UTC. */
export function formatClock(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${formatClock(iso)} UTC`;
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${pad(s % 60)}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${pad(m % 60)}m`;
  return `${Math.floor(h / 24)}d ${pad(h % 24)}h`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
}

export function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(ratio < 0.1 ? 2 : 1)}%`;
}

export function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1))}…`;
}

export const SEVERITY_HEX: Record<Severity, string> = {
  CRITICAL: "#f43f5e",
  ERROR: "#fb923c",
  WARNING: "#fbbf24",
  INFO: "#38bdf8",
  DEBUG: "#64748b",
};

export const SEVERITY_TEXT: Record<Severity, string> = {
  CRITICAL: "text-sev-critical",
  ERROR: "text-sev-error",
  WARNING: "text-sev-warning",
  INFO: "text-sev-info",
  DEBUG: "text-sev-debug",
};

export const INCIDENT_STYLE: Record<IncidentSeverity, string> = {
  none: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  low: "text-sky-300 border-sky-500/40 bg-sky-500/10",
  medium: "text-amber-300 border-amber-500/40 bg-amber-500/10",
  high: "text-orange-300 border-orange-500/40 bg-orange-500/10",
  critical: "text-rose-300 border-rose-500/40 bg-rose-500/10",
};

export const LEVEL_STYLE: Record<EvidenceLevel, string> = {
  strong: "text-emerald-300 border-emerald-500/40",
  moderate: "text-amber-300 border-amber-500/40",
  weak: "text-slate-300 border-slate-500/40",
};

export const VERDICT_LABEL: Record<Verdict, string> = {
  incident_detected: "Incident detected",
  no_incident: "No incident",
  insufficient_evidence: "Insufficient evidence",
};

export function toTitle(snake: string): string {
  return snake.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Axis label for a timeline bucket: time of day for short ranges, date + time for long ones. */
export function bucketLabel(iso: string, bucketSeconds: number): string {
  if (bucketSeconds >= 3600) {
    const d = new Date(iso);
    return `${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  }
  return formatClock(iso);
}
