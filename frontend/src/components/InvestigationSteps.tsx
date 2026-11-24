import type { RecommendedStep } from "../types/api";

export default function InvestigationSteps({ steps }: { steps: RecommendedStep[] }) {
  return (
    <section className="panel p-4" aria-label="Recommended investigation steps">
      <h2 className="panel-title">Recommended investigation steps</h2>
      {steps.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No investigation steps: no incident was detected.</p>
      ) : (
        <ol className="mt-3 space-y-2">
          {steps.map((s) => (
            <li key={s.priority} className="flex gap-3 text-sm">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-ink-600 text-[11px] font-semibold text-slate-300">
                {s.priority}
              </span>
              <span className="text-slate-300">{s.text}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
