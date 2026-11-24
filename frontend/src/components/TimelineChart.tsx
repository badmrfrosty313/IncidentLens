import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { sameWindow, windowFromBucket } from "../lib/filters";
import type { TimeWindow } from "../lib/filters";
import { SEVERITY_HEX, bucketLabel, formatDateTime } from "../lib/format";
import type { AnalysisResponse, Severity, TimelineBucket } from "../types/api";

interface Row {
  label: string;
  index: number;
  INFO: number;
  WARNING: number;
  ERROR: number;
  CRITICAL: number;
  DEBUG: number;
}

interface Props {
  analysis: AnalysisResponse;
  selected: TimeWindow | null;
  onSelect: (w: TimeWindow | null) => void;
}

const STACK: Severity[] = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];
const TOOLTIP_STYLE = { background: "#0b0f14", border: "1px solid #33445a", borderRadius: 6, fontSize: 12 };

export default function TimelineChart({ analysis, selected, onSelect }: Props) {
  const { timeline, bucket_seconds: size, spikes } = analysis;

  const rows: Row[] = useMemo(
    () =>
      timeline.map((b, index) => ({
        label: bucketLabel(b.start, size),
        index,
        DEBUG: b.counts.DEBUG,
        INFO: b.counts.INFO,
        WARNING: b.counts.WARNING,
        ERROR: b.counts.ERROR,
        CRITICAL: b.counts.CRITICAL,
      })),
    [timeline, size],
  );

  const spikeAreas = useMemo(
    () =>
      spikes
        .map((s) => {
          const first = timeline.findIndex((b) => b.end > s.start);
          const lastIdx = [...timeline].reverse().findIndex((b) => b.start < s.end);
          const last = lastIdx === -1 ? -1 : timeline.length - 1 - lastIdx;
          return first >= 0 && last >= first ? { x1: rows[first].label, x2: rows[last].label } : null;
        })
        .filter((a): a is { x1: string; x2: string } => a !== null),
    [spikes, timeline, rows],
  );

  function pick(row: Row) {
    const bucket: TimelineBucket | undefined = timeline[row.index];
    if (!bucket) return;
    const w = windowFromBucket(bucket);
    onSelect(sameWindow(selected, w) ? null : w);
  }

  if (timeline.length === 0) {
    return (
      <div className="panel p-4">
        <h2 className="panel-title">Event timeline</h2>
        <p className="mt-3 text-sm text-slate-500">No timestamped events, so no timeline can be drawn.</p>
      </div>
    );
  }

  return (
    <div className="panel p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="panel-title">Event timeline · {size}s buckets</h2>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          {selected ? (
            <>
              <span>
                Filtering log viewer: {formatDateTime(new Date(selected.start).toISOString())} →{" "}
                {formatDateTime(new Date(selected.end).toISOString())}
              </span>
              <button className="btn !py-0.5 !text-xs" onClick={() => onSelect(null)}>
                Clear time filter
              </button>
            </>
          ) : (
            <span>Click a bar to filter the log viewer to that interval</span>
          )}
        </div>
      </div>
      <div
        className="mt-3 h-56 w-full"
        role="img"
        aria-label={`Stacked bar timeline of ${analysis.summary.total_events} events; ${spikes.length} error spike(s) detected`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="#1a2430" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 10 }} minTickGap={24} stroke="#33445a" />
            <YAxis allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 10 }} stroke="#33445a" />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(148,163,184,0.08)" }} labelStyle={{ color: "#e2e8f0" }} />
            {spikeAreas.map((a, i) => (
              <ReferenceArea key={i} x1={a.x1} x2={a.x2} fill="#f43f5e" fillOpacity={0.12} stroke="#f43f5e" strokeOpacity={0.4} />
            ))}
            {STACK.map((sev) => (
              <Bar
                key={sev}
                dataKey={sev}
                stackId="events"
                fill={SEVERITY_HEX[sev]}
                fillOpacity={sev === "INFO" || sev === "DEBUG" ? 0.35 : 0.95}
                cursor="pointer"
                isAnimationActive={false}
                onClick={(d: unknown) => pick(d as Row)}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
        {(["CRITICAL", "ERROR", "WARNING", "INFO"] as Severity[]).map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ background: SEVERITY_HEX[s] }} />
            {s.toLowerCase()}
          </span>
        ))}
        {spikes.length > 0 && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-3 rounded-sm border border-sev-critical/60 bg-sev-critical/20" />
            error spike
          </span>
        )}
      </div>
    </div>
  );
}
