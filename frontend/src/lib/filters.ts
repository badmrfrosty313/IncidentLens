import type { LogEvent, Severity, TimelineBucket } from "../types/api";
import { SEVERITIES } from "../types/api";

export interface TimeWindow {
  /** inclusive epoch ms */
  start: number;
  /** exclusive epoch ms */
  end: number;
}

export interface LogFilter {
  query: string;
  severities: ReadonlySet<Severity>;
  service: string; // "" = all services
  window: TimeWindow | null;
}

export const ALL_SEVERITIES: ReadonlySet<Severity> = new Set(SEVERITIES);

export const emptyFilter = (): LogFilter => ({
  query: "",
  severities: new Set(ALL_SEVERITIES),
  service: "",
  window: null,
});

/** Case-insensitive substring match over message and service. Whitespace-separated terms are AND-ed. */
export function matchesQuery(e: LogEvent, query: string): boolean {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const hay = `${e.service} ${e.message}`.toLowerCase();
  return terms.every((t) => hay.includes(t));
}

export function filterEvents(events: readonly LogEvent[], f: LogFilter): LogEvent[] {
  return events.filter((e) => {
    if (!f.severities.has(e.severity)) return false;
    if (f.service && e.service !== f.service) return false;
    if (f.window) {
      // Events without a timestamp cannot be placed in a window.
      if (e.timestamp === null) return false;
      const t = Date.parse(e.timestamp);
      if (Number.isNaN(t) || t < f.window.start || t >= f.window.end) return false;
    }
    return matchesQuery(e, f.query);
  });
}

export function windowFromBucket(b: TimelineBucket): TimeWindow {
  return { start: Date.parse(b.start), end: Date.parse(b.end) };
}

export function sameWindow(a: TimeWindow | null, b: TimeWindow | null): boolean {
  if (a === null || b === null) return a === b;
  return a.start === b.start && a.end === b.end;
}

export function toggleSeverity(current: ReadonlySet<Severity>, s: Severity): Set<Severity> {
  const next = new Set(current);
  if (next.has(s)) next.delete(s);
  else next.add(s);
  return next;
}

export function uniqueServices(events: readonly LogEvent[]): string[] {
  return [...new Set(events.map((e) => e.service))].sort();
}
