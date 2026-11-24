import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { SEVERITY_HEX, formatPercent } from "../lib/format";
import { SEVERITIES } from "../types/api";
import type { Severity } from "../types/api";

export default function SeverityChart({ distribution }: { distribution: Record<Severity, number> }) {
  const total = SEVERITIES.reduce((n, s) => n + (distribution[s] ?? 0), 0);
  const data = SEVERITIES.filter((s) => (distribution[s] ?? 0) > 0).map((s) => ({ name: s, value: distribution[s] }));

  return (
    <div className="panel p-4">
      <h2 className="panel-title">Severity distribution</h2>
      <div className="mt-2 flex items-center gap-4">
        <div className="h-36 w-36 shrink-0" role="img" aria-label="Severity distribution donut chart">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="name" innerRadius={38} outerRadius={64} stroke="#0b0f14" strokeWidth={2} isAnimationActive={false}>
                {data.map((d) => (
                  <Cell key={d.name} fill={SEVERITY_HEX[d.name]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "#0b0f14", border: "1px solid #33445a", borderRadius: 6, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="min-w-0 flex-1 space-y-1 text-sm">
          {[...SEVERITIES].reverse().map((s) => (
            <li key={s} className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-2 text-slate-300">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: SEVERITY_HEX[s] }} />
                {s}
              </span>
              <span className="tabular-nums text-slate-400">
                {(distribution[s] ?? 0).toLocaleString()}
                <span className="ml-2 text-xs text-slate-600">{total ? formatPercent((distribution[s] ?? 0) / total) : "—"}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
