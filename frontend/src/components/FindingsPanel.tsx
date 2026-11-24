import { formatClock, formatDateTime, formatDuration } from "../lib/format";
import type { AnalysisResponse } from "../types/api";

export default function FindingsPanel({ analysis }: { analysis: AnalysisResponse }) {
  const { spikes, cascade, correlations, exception_patterns: patterns, ingest } = analysis;
  const recurring = patterns.filter((p) => p.recurring).slice(0, 5);
  const redactions = Object.entries(ingest.redactions);

  return (
    <section className="panel space-y-4 p-4" aria-label="Correlation findings">
      <h2 className="panel-title">Temporal findings</h2>

      <div>
        <h3 className="mb-1 text-sm font-medium text-slate-200">Error spikes</h3>
        {spikes.length === 0 ? (
          <p className="text-sm text-slate-500">No error spike above the quiet baseline.</p>
        ) : (
          <ul className="space-y-1 text-sm text-slate-300">
            {spikes.map((s) => (
              <li key={s.start}>
                <span className="font-mono text-xs text-sev-critical">
                  {formatClock(s.start)}–{formatClock(s.end)}
                </span>{" "}
                {s.total_errors} errors, peak {s.peak_count}/bucket (baseline {s.baseline}, threshold {s.threshold}) · {s.services.join(", ")}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-1 text-sm font-medium text-slate-200">Cascading failure</h3>
        {cascade === null ? (
          <p className="text-sm text-slate-500">No multi-wave cascade detected.</p>
        ) : (
          <>
            <p className="text-sm text-slate-300">{cascade.note}</p>
            <ol className="mt-2 space-y-1">
              {cascade.steps.map((st) => (
                <li key={st.service} className="flex items-center gap-2 text-xs">
                  <span className="w-14 shrink-0 text-right font-mono tabular-nums text-slate-500">+{formatDuration(st.offset_seconds)}</span>
                  <span className="h-2 w-2 shrink-0 rounded-full bg-sev-critical" aria-hidden="true" />
                  <span className="font-mono text-accent">{st.service}</span>
                  <span className="text-slate-500">
                    wave {st.wave} · {st.error_count} errors · from {formatDateTime(st.onset)}
                  </span>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>

      {correlations.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-medium text-slate-200">Correlated services</h3>
          <ul className="space-y-0.5 text-sm text-slate-300">
            {correlations.slice(0, 4).map((c) => (
              <li key={`${c.service_a}-${c.service_b}`}>
                {c.interpretation} <span className="text-xs text-slate-500">(r = {c.correlation.toFixed(2)})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {recurring.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-medium text-slate-200">Recurring exception patterns</h3>
          <ul className="flex flex-wrap gap-1.5">
            {recurring.map((p) => (
              <li key={p.name} className="chip" title={`${p.count} occurrences across ${p.buckets_present} time buckets`}>
                {p.name} × {p.count}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="border-t border-ink-600 pt-3 text-xs text-slate-500">
        <p>
          Parsed {ingest.parsed_records.toLocaleString()} of {ingest.total_records.toLocaleString()} records as <strong className="text-slate-300">{ingest.detected_format}</strong>
          {ingest.malformed_records > 0 && <> · {ingest.malformed_records} malformed skipped</>}
        </p>
        <p className="mt-0.5">
          Redactions applied:{" "}
          {redactions.length === 0 ? "none" : redactions.map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(", ")}
        </p>
        {ingest.warnings.map((w) => (
          <p key={w} className="mt-0.5 text-amber-400/80">
            ⚠ {w}
          </p>
        ))}
      </div>
    </section>
  );
}
