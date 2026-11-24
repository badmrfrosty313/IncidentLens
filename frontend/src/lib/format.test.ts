import { describe, expect, it } from "vitest";
import { bucketLabel, formatBytes, formatClock, formatDateTime, formatDuration, formatPercent, toTitle, truncate } from "./format";
import { checkExpected } from "./expected";
import { reportFilename } from "./download";
import { SCENARIO, makeAnalysis } from "../test/fixtures";

describe("format", () => {
  it("formats clocks and datetimes in UTC", () => {
    expect(formatClock("2025-03-14T09:05:07Z")).toBe("09:05:07");
    expect(formatDateTime("2025-03-14T09:05:07Z")).toBe("2025-03-14 09:05:07 UTC");
    expect(formatClock(null)).toBe("—");
    expect(formatClock("garbage")).toBe("—");
  });

  it("formats durations", () => {
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(125)).toBe("2m 05s");
    expect(formatDuration(3700)).toBe("1h 01m");
    expect(formatDuration(-1)).toBe("—");
  });

  it("formats bytes, percents, truncation, titles", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KiB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MiB");
    expect(formatPercent(0.0123)).toBe("1.23%");
    expect(formatPercent(0.25)).toBe("25.0%");
    expect(truncate("abcdef", 4)).toBe("abc…");
    expect(truncate("abc", 4)).toBe("abc");
    expect(toTitle("db_pool_exhaustion")).toBe("Db pool exhaustion");
  });

  it("labels buckets by time or date depending on bucket size", () => {
    expect(bucketLabel("2025-03-14T09:05:07Z", 30)).toBe("09:05:07");
    expect(bucketLabel("2025-03-14T09:05:07Z", 3600)).toBe("03-14 09:05");
  });

  it("builds safe report filenames (no path separators, always prefixed)", () => {
    expect(reportFilename("My Logs (prod).log", "markdown")).toBe("incident-report-my-logs-prod-.log.md");
    const hostile = reportFilename("../../etc/passwd", "json");
    expect(hostile).toBe("incident-report-..-..-etc-passwd.json");
    expect(hostile).not.toMatch(/[\\/]/);
    expect(reportFilename("***", "json")).toBe("incident-report-incident-report.json");
  });
});

describe("checkExpected", () => {
  it("passes when the analysis matches", () => {
    expect(checkExpected(SCENARIO.expected, makeAnalysis())).toEqual([]);
  });

  it("reports mismatches", () => {
    const a = makeAnalysis({ verdict: "no_incident", hypotheses: [], spikes: [] });
    const problems = checkExpected(SCENARIO.expected, a);
    expect(problems.some((p) => p.includes("verdict"))).toBe(true);
    expect(problems.some((p) => p.includes("top hypothesis"))).toBe(true);
    expect(problems.some((p) => p.includes("spike"))).toBe(true);
  });
});
