import { useState } from "react";
import { fetchReport } from "../lib/api";
import { REPORT_MIME, reportFilename, saveText } from "../lib/download";
import type { AnalysisSource, ReportFormat } from "../types/api";

interface Props {
  source: AnalysisSource | null;
}

export default function ExportButtons({ source }: Props) {
  const [busy, setBusy] = useState<ReportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(format: ReportFormat) {
    if (!source) return;
    setBusy(format);
    setError(null);
    try {
      const text = await fetchReport(source, format);
      const stem = source.kind === "demo" ? source.scenarioId : source.label;
      saveText(reportFilename(stem, format), text, REPORT_MIME[format]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button className="btn" disabled={!source || busy !== null} onClick={() => void run("markdown")}>
        {busy === "markdown" ? "Preparing…" : "Export Markdown"}
      </button>
      <button className="btn" disabled={!source || busy !== null} onClick={() => void run("json")}>
        {busy === "json" ? "Preparing…" : "Export JSON"}
      </button>
      {error && (
        <span role="alert" className="text-xs text-rose-400">
          {error}
        </span>
      )}
    </div>
  );
}
