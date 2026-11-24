import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SEVERITY_HEX, truncate } from "../lib/format";
import type { ErrorGroup } from "../types/api";

const TOP = 8;

export default function ErrorFrequencyChart({ groups }: { groups: ErrorGroup[] }) {
  const errorGroups = groups.filter((g) => g.severity === "ERROR" || g.severity === "CRITICAL");
  const shown = (errorGroups.length > 0 ? errorGroups : groups).slice(0, TOP);
  const data = shown.map((g) => ({ label: truncate(g.signature, 34), full: g.signature, count: g.count, severity: g.severity }));

  return (
    <div className="panel p-4">
      <h2 className="panel-title">{errorGroups.length > 0 ? "Error frequency · top patterns" : "Warning frequency · top patterns"}</h2>
      {data.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No warnings or errors were found.</p>
      ) : (
        <div className="mt-2" style={{ height: 28 * data.length + 36 }} role="img" aria-label="Bar chart of the most frequent error message patterns">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#1a2430" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 10 }} stroke="#33445a" />
              <YAxis type="category" dataKey="label" width={210} tick={{ fill: "#cbd5e1", fontSize: 10 }} stroke="#33445a" />
              <Tooltip
                contentStyle={{ background: "#0b0f14", border: "1px solid #33445a", borderRadius: 6, fontSize: 12 }}
                cursor={{ fill: "rgba(148,163,184,0.08)" }}
                formatter={(value) => [String(value), "occurrences"]}
                labelFormatter={(_label, payload) => (payload?.[0]?.payload as { full?: string } | undefined)?.full ?? ""}
              />
              <Bar dataKey="count" isAnimationActive={false} radius={[0, 3, 3, 0]}>
                {data.map((d) => (
                  <Cell key={d.full} fill={SEVERITY_HEX[d.severity]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
