import type { ReportFormat } from "../types/api";

export const REPORT_MIME: Record<ReportFormat, string> = {
  markdown: "text/markdown;charset=utf-8",
  json: "application/json;charset=utf-8",
};

export const REPORT_EXTENSION: Record<ReportFormat, string> = { markdown: "md", json: "json" };

export function reportFilename(stem: string, format: ReportFormat): string {
  const safe = stem.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "incident-report";
  return `incident-report-${safe}.${REPORT_EXTENSION[format]}`;
}

/** Trigger a browser download of text content. */
export function saveText(filename: string, text: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
