import { describe, expect, it } from "vitest";
import { EVENTS } from "../test/fixtures";
import { emptyFilter, filterEvents, matchesQuery, sameWindow, toggleSeverity, uniqueServices, windowFromBucket } from "./filters";
import type { Severity } from "../types/api";

describe("filterEvents", () => {
  it("returns everything for the empty filter", () => {
    expect(filterEvents(EVENTS, emptyFilter())).toHaveLength(EVENTS.length);
  });

  it("matches search terms case-insensitively over service and message, AND-ing terms", () => {
    expect(filterEvents(EVENTS, { ...emptyFilter(), query: "POOL" }).map((e) => e.id)).toEqual([1, 2]);
    expect(filterEvents(EVENTS, { ...emptyFilter(), query: "orders-api timeout" }).map((e) => e.id)).toEqual([2]);
    expect(filterEvents(EVENTS, { ...emptyFilter(), query: "nothing matches this" })).toEqual([]);
  });

  it("filters by severity set", () => {
    const f = { ...emptyFilter(), severities: new Set<Severity>(["ERROR", "CRITICAL"]) };
    expect(filterEvents(EVENTS, f).map((e) => e.id)).toEqual([2, 3, 4]);
    expect(filterEvents(EVENTS, { ...f, severities: new Set<Severity>() })).toEqual([]);
  });

  it("filters by service", () => {
    expect(filterEvents(EVENTS, { ...emptyFilter(), service: "api-gateway" }).map((e) => e.id)).toEqual([0, 3]);
  });

  it("filters by time window (start inclusive, end exclusive)", () => {
    const t0 = Date.parse(EVENTS[0].timestamp as string);
    const w = { start: t0 + 10_000, end: t0 + 30_000 };
    expect(filterEvents(EVENTS, { ...emptyFilter(), window: w }).map((e) => e.id)).toEqual([1, 2]);
  });

  it("excludes events without a timestamp when a window is active", () => {
    const undated = { ...EVENTS[0], id: 99, timestamp: null };
    const w = { start: 0, end: Number.MAX_SAFE_INTEGER };
    expect(filterEvents([undated], { ...emptyFilter(), window: w })).toEqual([]);
    expect(filterEvents([undated], emptyFilter())).toHaveLength(1);
  });

  it("combines all filters", () => {
    const f = { ...emptyFilter(), query: "connection", service: "orders-api", severities: new Set<Severity>(["ERROR"]) };
    expect(filterEvents(EVENTS, f).map((e) => e.id)).toEqual([2]);
  });
});

describe("helpers", () => {
  it("matchesQuery ignores empty / whitespace queries", () => {
    expect(matchesQuery(EVENTS[0], "   ")).toBe(true);
  });

  it("toggleSeverity does not mutate its input", () => {
    const base = new Set<Severity>(["INFO"]);
    const next = toggleSeverity(base, "ERROR");
    expect([...base]).toEqual(["INFO"]);
    expect(next.has("ERROR")).toBe(true);
    expect(toggleSeverity(next, "ERROR").has("ERROR")).toBe(false);
  });

  it("uniqueServices is sorted and distinct", () => {
    expect(uniqueServices(EVENTS)).toEqual(["api-gateway", "billing-api", "orders-api", "orders-db-proxy"]);
  });

  it("window helpers", () => {
    const w = windowFromBucket({ start: "2025-03-14T09:00:00Z", end: "2025-03-14T09:00:30Z", counts: { DEBUG: 0, INFO: 0, WARNING: 0, ERROR: 0, CRITICAL: 0 }, total: 0 });
    expect(w.end - w.start).toBe(30_000);
    expect(sameWindow(w, { ...w })).toBe(true);
    expect(sameWindow(w, null)).toBe(false);
    expect(sameWindow(null, null)).toBe(true);
  });
});
