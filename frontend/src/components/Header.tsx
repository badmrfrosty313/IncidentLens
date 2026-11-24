export type ApiStatus = "checking" | "online" | "offline" | "static";

interface Props {
  status: ApiStatus;
  version?: string;
}

const DOT: Record<ApiStatus, string> = {
  checking: "bg-slate-500",
  online: "bg-emerald-400",
  offline: "bg-rose-500",
  static: "bg-amber-400",
};

export default function Header({ status, version }: Props) {
  return (
    <header className="border-b border-ink-600 bg-ink-950/80 backdrop-blur">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-3">
          <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
            <circle cx="12" cy="12" r="8" fill="none" stroke="#22d3ee" strokeWidth="2" />
            <path d="M18 18l6 6" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round" />
            <path d="M7 12h3l2-4 2 8 2-4h1" fill="none" stroke="#22d3ee" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
          <div>
            <h1 className="text-base font-semibold leading-none tracking-tight text-white">IncidentLens</h1>
            <p className="mt-1 text-xs text-slate-400">Raw logs → incident report. Deterministic analysis, no API keys, no LLM.</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400" role="status" aria-live="polite">
          <span className={`h-2 w-2 rounded-full ${DOT[status]}`} aria-hidden="true" />
          <span>
            {status === "static" ? "Static demo" : `API ${status === "checking" ? "checking…" : status}`}
            {(status === "online" || status === "static") && version ? ` · v${version}` : ""}
          </span>
        </div>
      </div>
    </header>
  );
}
