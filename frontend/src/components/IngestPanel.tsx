import { useRef, useState } from "react";
import type { DragEvent, KeyboardEvent } from "react";
import { MAX_UPLOAD_BYTES } from "../lib/api";
import { formatBytes } from "../lib/format";
import { REPO_URL, isStaticDemo } from "../lib/mode";
import type { FormatHint, ScenarioInfo } from "../types/api";

type Tab = "upload" | "paste" | "demo";

interface Props {
  scenarios: ScenarioInfo[];
  busy: boolean;
  activeScenarioId: string | null;
  onAnalyze: (content: string, format: FormatHint, label: string) => void;
  onSelectScenario: (id: string) => void;
}

const FORMATS: { value: FormatHint; label: string }[] = [
  { value: "auto", label: "Auto-detect" },
  { value: "plaintext", label: "Plaintext" },
  { value: "json", label: "JSON array" },
  { value: "jsonl", label: "JSONL" },
];

export function readFileText(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("Could not read file"));
    reader.readAsText(file);
  });
}

export default function IngestPanel({ scenarios, busy, activeScenarioId, onAnalyze, onSelectScenario }: Props) {
  const staticDemo = isStaticDemo();
  const [tab, setTab] = useState<Tab>("demo");
  const [format, setFormat] = useState<FormatHint>("auto");
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const textBytes = new Blob([text]).size;
  const tooLarge = textBytes > MAX_UPLOAD_BYTES;

  async function handleFile(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setError(`${file.name} is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`);
      return;
    }
    try {
      const content = await readFileText(file);
      if (!content.trim()) {
        setError(`${file.name} is empty.`);
        return;
      }
      onAnalyze(content, format, file.name);
    } catch {
      setError(`Could not read ${file.name}.`);
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    void handleFile(e.dataTransfer.files?.[0]);
  }

  function onZoneKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.current?.click();
    }
  }

  const tabButton = (id: Tab, label: string) => (
    <button
      role="tab"
      aria-selected={tab === id}
      disabled={staticDemo && id !== "demo"}
      title={staticDemo && id !== "demo" ? "Disabled in the static demonstration: run IncidentLens locally to analyze your own logs" : undefined}
      onClick={() => setTab(id)}
      className={`flex-1 border-b-2 px-2 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
        tab === id ? "border-accent text-white" : "border-transparent text-slate-400 hover:text-slate-200"
      }`}
    >
      {label}
    </button>
  );

  return (
    <section className="panel" aria-label="Log ingestion">
      <div role="tablist" className="flex border-b border-ink-600">
        {tabButton("demo", "Demo scenarios")}
        {tabButton("upload", "Upload")}
        {tabButton("paste", "Manual entry")}
      </div>

      <div className="space-y-3 p-3">
        {tab !== "demo" && (
          <label className="flex items-center justify-between gap-2 text-xs text-slate-400">
            Format
            <select
              aria-label="Log format"
              value={format}
              onChange={(e) => setFormat(e.target.value as FormatHint)}
              className="rounded border border-ink-500 bg-ink-700 px-2 py-1 text-sm text-slate-200"
            >
              {FORMATS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
        )}

        {tab === "upload" && (
          <div
            role="button"
            tabIndex={0}
            aria-label="Drop a log file here or press Enter to choose one"
            onClick={() => fileInput.current?.click()}
            onKeyDown={onZoneKey}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed px-4 py-8 text-center text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              dragging ? "border-accent bg-accent/10" : "border-ink-500 hover:border-slate-400"
            }`}
          >
            <span className="font-medium text-slate-200">Drag &amp; drop a log file</span>
            <span className="text-xs text-slate-400">.log .txt .json .jsonl · up to {formatBytes(MAX_UPLOAD_BYTES)}</span>
            <input
              ref={fileInput}
              data-testid="file-input"
              type="file"
              className="hidden"
              accept=".log,.txt,.json,.jsonl,.ndjson,text/plain,application/json"
              onChange={(e) => {
                void handleFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </div>
        )}

        {tab === "paste" && (
          <>
            <textarea
              aria-label="Log content"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"2025-03-14T09:00:00Z ERROR [orders-api] connection pool exhausted\n{\"level\":\"error\",\"service\":\"api\",\"message\":\"timeout\"}"}
              spellCheck={false}
              rows={9}
              className="w-full resize-y rounded-md border border-ink-500 bg-ink-900 p-2 font-mono text-xs text-slate-200 placeholder:text-slate-600 focus:border-accent focus:outline-none"
            />
            <div className="flex items-center justify-between gap-2">
              <span className={`text-xs ${tooLarge ? "text-rose-400" : "text-slate-500"}`}>
                {formatBytes(textBytes)} / {formatBytes(MAX_UPLOAD_BYTES)}
              </span>
              <div className="flex gap-2">
                <button className="btn" onClick={() => setText("")} disabled={!text}>
                  Clear
                </button>
                <button
                  className="btn btn-primary"
                  disabled={busy || !text.trim() || tooLarge}
                  onClick={() => onAnalyze(text, format, "manual entry")}
                >
                  {busy ? "Analyzing…" : "Analyze"}
                </button>
              </div>
            </div>
          </>
        )}

        {tab === "demo" && (
          <ul className="space-y-2">
            {scenarios.length === 0 && <li className="text-sm text-slate-500">Loading scenarios…</li>}
            {scenarios.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => onSelectScenario(s.id)}
                  disabled={busy}
                  aria-pressed={activeScenarioId === s.id}
                  className={`w-full rounded-md border px-3 py-2 text-left transition disabled:opacity-60 ${
                    activeScenarioId === s.id ? "border-accent bg-accent/10" : "border-ink-500 bg-ink-800 hover:border-slate-400"
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-slate-100">{s.name}</span>
                    <span className="chip">{s.format}</span>
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-400">{s.description}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {error && (
          <p role="alert" className="rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-300">
            {error}
          </p>
        )}
        {staticDemo ? (
          <div role="note" data-testid="static-demo-help" className="space-y-1.5 rounded border border-amber-400/30 bg-amber-400/5 p-2 text-[11px] leading-snug text-slate-300">
            <p>
              <strong className="text-amber-300">Upload and manual entry are disabled</strong> in this static demonstration. These results were
              produced by the Python engine at build time; no server is involved and nothing you do here is sent anywhere.
            </p>
            <p>To analyze your own logs, run the full application locally:</p>
            <pre className="overflow-x-auto rounded bg-ink-900 p-1.5 font-mono text-[10px] text-slate-300">{`git clone ${REPO_URL}.git
cd IncidentLens
docker compose up --build
# then open http://localhost:8080`}</pre>
          </div>
        ) : (
          <p className="text-[11px] leading-snug text-slate-500">
            Logs are analyzed in memory by the local backend, which stores nothing and calls no external service. Redaction of common secrets is pattern-based and best-effort: it can miss secrets it has no pattern for.
          </p>
        )}
      </div>
    </section>
  );
}
