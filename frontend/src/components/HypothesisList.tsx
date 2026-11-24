import { useState } from "react";
import { LEVEL_STYLE, SEVERITY_TEXT, VERDICT_LABEL, formatClock, formatDateTime } from "../lib/format";
import type { AnalysisResponse, Hypothesis } from "../types/api";

function ScoreBar({ score }: { score: number }) {
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded bg-ink-600"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score}
      aria-label="Heuristic evidence score"
    >
      <div className="h-full rounded bg-accent" style={{ width: `${Math.max(2, Math.min(100, score))}%` }} />
    </div>
  );
}

function HypothesisCard({ h, defaultOpen }: { h: Hypothesis; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = `hyp-${h.category}`;
  return (
    <li className="rounded-md border border-ink-600 bg-ink-850">
      <button
        className="flex w-full items-start gap-3 p-3 text-left"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-accent-dim bg-accent-dim/30 text-xs font-semibold text-accent">
          {h.rank}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-white">{h.title}</span>
            <span className={`rounded border px-1.5 py-0.5 text-[11px] uppercase tracking-wide ${LEVEL_STYLE[h.evidence_level]}`}>{h.evidence_level} evidence</span>
          </span>
          <span className="mt-2 flex items-center gap-3">
            <span className="w-28 shrink-0 text-xs tabular-nums text-slate-300">
              Score <strong className="text-white">{h.evidence_score.toFixed(1)}</strong>/100
            </span>
            <ScoreBar score={h.evidence_score} />
          </span>
          <span className="mt-2 flex flex-wrap gap-1.5">
            {h.affected_services.slice(0, 5).map((s) => (
              <span key={s.name} className="chip" title={`${s.matched_events} matching events`}>
                {s.name} · {s.matched_events}
              </span>
            ))}
          </span>
        </span>
        <span aria-hidden="true" className="text-slate-500">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div id={panelId} className="space-y-4 border-t border-ink-600 p-3 text-sm">
          <p className="text-slate-300">{h.summary}</p>

          <div>
            <h3 className="panel-title mb-1.5">Supporting evidence</h3>
            <ul className="space-y-1">
              {h.evidence.map((e) => (
                <li key={e.event_id} className="rounded border border-ink-600 bg-ink-900 px-2 py-1.5 font-mono text-xs">
                  <span className="text-slate-500">{formatClock(e.timestamp)}</span>{" "}
                  <span className={SEVERITY_TEXT[e.severity]}>{e.severity}</span>{" "}
                  <span className="text-accent">{e.service}</span>{" "}
                  <span className="break-words text-slate-200">{e.message}</span>
                  <span className="ml-2 text-[10px] uppercase text-slate-500">[{e.indicator}]</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="panel-title mb-1.5">How the score was computed</h3>
            <table className="w-full text-xs">
              <thead className="text-left text-slate-500">
                <tr>
                  <th className="py-1 font-medium">Factor</th>
                  <th className="py-1 text-right font-medium">Points</th>
                  <th className="py-1 pl-3 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {h.score_breakdown.map((c) => (
                  <tr key={c.factor} className="border-t border-ink-700">
                    <td className="py-1 text-slate-300">{c.factor}</td>
                    <td className="py-1 text-right tabular-nums text-slate-200">
                      {c.points}/{c.max_points}
                    </td>
                    <td className="py-1 pl-3 text-slate-400">{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-[11px] text-slate-500">
              {formatDateTime(h.first_seen)} → {formatClock(h.last_seen)} · {h.matched_events} matching events
            </p>
          </div>

          <div>
            <h3 className="panel-title mb-1.5">Recommended diagnostic actions</h3>
            <ol className="list-decimal space-y-1 pl-5 text-slate-300">
              {h.recommended_actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </li>
  );
}

export default function HypothesisList({ analysis }: { analysis: AnalysisResponse }) {
  const { hypotheses, verdict, verdict_reason, score_note } = analysis;
  return (
    <section className="panel p-4" aria-label="Root-cause hypotheses">
      <h2 className="panel-title">Ranked root-cause hypotheses</h2>
      {hypotheses.length === 0 ? (
        <div role="status" className="mt-3 rounded-md border border-ink-600 bg-ink-850 p-3 text-sm">
          <p className="font-semibold text-white">{VERDICT_LABEL[verdict]}</p>
          <p className="mt-1 text-slate-400">{verdict_reason}</p>
        </div>
      ) : (
        <>
          <p className="mt-2 text-xs text-slate-500">{score_note}</p>
          <ul className="mt-3 space-y-2">
            {hypotheses.map((h) => (
              <HypothesisCard key={h.category} h={h} defaultOpen={h.rank === 1} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
