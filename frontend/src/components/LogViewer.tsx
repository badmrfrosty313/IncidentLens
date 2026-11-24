import { useEffect, useMemo, useState } from "react";
import { emptyFilter, filterEvents, toggleSeverity, uniqueServices } from "../lib/filters";
import type { TimeWindow } from "../lib/filters";
import { SEVERITY_TEXT, formatClock, formatDateTime } from "../lib/format";
import { SEVERITIES } from "../types/api";
import type { LogEvent, Severity } from "../types/api";

const PAGE = 200;

interface Props {
  events: LogEvent[];
  total: number;
  truncated: boolean;
  window: TimeWindow | null;
  onClearWindow: () => void;
}

export default function LogViewer({ events, total, truncated, window, onClearWindow }: Props) {
  const [query, setQuery] = useState("");
  const [severities, setSeverities] = useState<ReadonlySet<Severity>>(() => emptyFilter().severities);
  const [service, setService] = useState("");
  const [visible, setVisible] = useState(PAGE);

  const services = useMemo(() => uniqueServices(events), [events]);
  const matches = useMemo(
    () => filterEvents(events, { query, severities, service, window }),
    [events, query, severities, service, window],
  );

  // Any filter change returns the list to its first page.
  useEffect(() => setVisible(PAGE), [query, severities, service, window, events]);

  const pristine = query === "" && service === "" && severities.size === SEVERITIES.length;
  const reset = () => {
    setQuery("");
    setService("");
    setSeverities(emptyFilter().severities);
  };

  return (
    <section className="panel" aria-label="Log viewer">
      <div className="flex flex-wrap items-center gap-2 border-b border-ink-600 p-3">
        <h2 className="panel-title mr-2">Log viewer</h2>
        <input
          type="search"
          aria-label="Search logs"
          placeholder="Search message or service…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="min-w-[12rem] flex-1 rounded-md border border-ink-500 bg-ink-900 px-2.5 py-1.5 text-sm placeholder:text-slate-600 focus:border-accent focus:outline-none"
        />
        <select
          aria-label="Filter by service"
          value={service}
          onChange={(e) => setService(e.target.value)}
          className="rounded-md border border-ink-500 bg-ink-700 px-2 py-1.5 text-sm"
        >
          <option value="">All services</option>
          {services.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <div className="flex gap-1" role="group" aria-label="Filter by severity">
          {SEVERITIES.map((s) => {
            const on = severities.has(s);
            return (
              <button
                key={s}
                aria-pressed={on}
                onClick={() => setSeverities((cur) => toggleSeverity(cur, s))}
                className={`rounded border px-2 py-1 text-[11px] font-semibold transition ${
                  on ? `border-ink-500 bg-ink-700 ${SEVERITY_TEXT[s]}` : "border-ink-700 bg-transparent text-slate-600"
                }`}
              >
                {s}
              </button>
            );
          })}
        </div>
        <button className="btn !py-1" onClick={reset} disabled={pristine}>
          Reset
        </button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs text-slate-400" role="status">
        <span>
          {matches.length.toLocaleString()} matching · {events.length.toLocaleString()} loaded of {total.toLocaleString()} analyzed
        </span>
        {window && (
          <span className="inline-flex items-center gap-2">
            Interval {formatDateTime(new Date(window.start).toISOString())} → {formatClock(new Date(window.end).toISOString())}
            <button className="btn !py-0.5 !text-xs" onClick={onClearWindow}>
              Clear
            </button>
          </span>
        )}
      </div>
      {truncated && (
        <p className="mx-3 mb-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-300">
          Showing {events.length.toLocaleString()} of {total.toLocaleString()} events. All warnings and errors are prioritized; informational events are sampled.
        </p>
      )}

      <div className="max-h-[28rem] overflow-auto border-t border-ink-600">
        {matches.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">No events match the current filters.</p>
        ) : (
          <table className="w-full min-w-[40rem] border-collapse text-left font-mono text-xs">
            <thead className="sticky top-0 bg-ink-800 text-slate-500">
              <tr>
                <th className="px-3 py-1.5 font-medium">Time (UTC)</th>
                <th className="px-2 py-1.5 font-medium">Level</th>
                <th className="px-2 py-1.5 font-medium">Service</th>
                <th className="px-2 py-1.5 font-medium">Message</th>
              </tr>
            </thead>
            <tbody>
              {matches.slice(0, visible).map((e) => (
                <tr key={e.id} data-testid="log-row" className="border-t border-ink-700/70 align-top hover:bg-ink-700/40">
                  <td className="whitespace-nowrap px-3 py-1 text-slate-500">{formatClock(e.timestamp)}</td>
                  <td className={`px-2 py-1 font-semibold ${SEVERITY_TEXT[e.severity]}`}>{e.severity}</td>
                  <td className="whitespace-nowrap px-2 py-1 text-accent">{e.service}</td>
                  <td className="break-words px-2 py-1 text-slate-200" title={e.message}>
                    {e.message.length > 400 ? `${e.message.slice(0, 399)}…` : e.message}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {matches.length > visible && (
        <div className="border-t border-ink-600 p-2 text-center">
          <button className="btn" onClick={() => setVisible((v) => v + PAGE)}>
            Show {Math.min(PAGE, matches.length - visible)} more
          </button>
        </div>
      )}
    </section>
  );
}
