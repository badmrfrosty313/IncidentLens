import { INCIDENT_STYLE, VERDICT_LABEL, formatDuration, formatPercent } from "../lib/format";
import type { AnalysisResponse } from "../types/api";

function Card({ label, value, sub, valueClass = "text-white" }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="panel px-3 py-2.5">
      <p className="panel-title">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${valueClass}`}>{value}</p>
      {sub && <p className="mt-0.5 truncate text-xs text-slate-500" title={sub}>{sub}</p>}
    </div>
  );
}

export default function StatCards({ analysis }: { analysis: AnalysisResponse }) {
  const s = analysis.summary;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" aria-label="Key metrics">
      <Card label="Events analyzed" value={s.total_events.toLocaleString()} sub={`${formatDuration(s.time_range.duration_seconds)} window`} />
      <Card label="Errors" value={s.error_count.toLocaleString()} sub={`${formatPercent(s.error_ratio)} of events · ${s.critical_count} critical`} valueClass={s.error_count ? "text-sev-error" : "text-white"} />
      <Card label="Warnings" value={s.warning_count.toLocaleString()} valueClass={s.warning_count ? "text-sev-warning" : "text-white"} />
      <Card label="Affected services" value={String(s.affected_services.length)} sub={s.affected_services.slice(0, 3).join(", ") || "none"} />
      <div className={`panel border px-3 py-2.5 ${INCIDENT_STYLE[s.incident_severity]}`}>
        <p className="panel-title !text-current opacity-80">Incident severity</p>
        <p className="mt-1 text-2xl font-semibold capitalize">{s.incident_severity}</p>
      </div>
      <Card label="Verdict" value={VERDICT_LABEL[analysis.verdict]} valueClass="text-base leading-8 text-white" />
    </div>
  );
}
