import { checkExpected } from "../lib/expected";
import { toTitle } from "../lib/format";
import type { AnalysisResponse, ScenarioInfo } from "../types/api";

export default function ExpectedOutcomeCard({ scenario, analysis }: { scenario: ScenarioInfo; analysis: AnalysisResponse }) {
  const problems = checkExpected(scenario.expected, analysis);
  const e = scenario.expected;
  return (
    <section className="panel p-3 text-sm" aria-label="Expected outcome">
      <h2 className="panel-title">Documented expected outcome</h2>
      <p className="mt-2 text-slate-300">{e.description}</p>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="text-slate-500">Verdict</dt>
        <dd>{toTitle(e.verdict)}</dd>
        <dt className="text-slate-500">Top hypothesis</dt>
        <dd>{e.top_hypothesis ? toTitle(e.top_hypothesis) : "none"}</dd>
        <dt className="text-slate-500">Spike / cascade</dt>
        <dd>
          {e.expect_spike ? "spike" : "no spike"} · {e.expect_cascade ? "cascade" : "no cascade"}
        </dd>
      </dl>
      {problems.length === 0 ? (
        <p role="status" className="mt-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-300">
          ✓ The engine's output matches this expectation.
        </p>
      ) : (
        <ul role="alert" className="mt-3 list-disc rounded border border-rose-500/30 bg-rose-500/10 py-1 pl-5 pr-2 text-xs text-rose-300">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
