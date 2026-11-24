import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartPlan, ChartType } from "../utils/charts";
import { cn } from "../utils/format";

const COLORS = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#14b8a6", "#64748b"];

export function ChartPanel({ plan }: { plan: ChartPlan }) {
  const [type, setType] = useState<ChartType>(plan.type);
  const options = [plan.type, ...plan.alternatives.filter((t) => t !== plan.type)];

  return (
    <div className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-slate-500">
          {plan.reason}
          {plan.truncated && " Showing the first 30 rows."}
        </p>
        {options.length > 1 && (
          <div role="group" aria-label="Chart type" className="inline-flex rounded-lg bg-slate-100 p-0.5 text-xs">
            {options.map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={t === type}
                onClick={() => setType(t)}
                className={cn("rounded-md px-2.5 py-1 font-medium capitalize", t === type ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800")}
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="h-72 w-full" data-testid={`chart-${type}`}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          {type === "pie" ? (
            <PieChart>
              <Pie data={plan.data} dataKey={plan.valueKeys[0]} nameKey={plan.labelKey} outerRadius="80%" label>
                {plan.data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          ) : type === "line" ? (
            <LineChart data={plan.data} margin={{ left: 8, right: 16, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey={plan.labelKey} tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} width={64} />
              <Tooltip />
              {plan.valueKeys.length > 1 && <Legend />}
              {plan.valueKeys.map((k, i) => (
                <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={{ r: 2 }} />
              ))}
            </LineChart>
          ) : (
            <BarChart data={plan.data} margin={{ left: 8, right: 16, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey={plan.labelKey} tick={{ fontSize: 11 }} interval={0} angle={plan.data.length > 8 ? -35 : 0} textAnchor={plan.data.length > 8 ? "end" : "middle"} height={plan.data.length > 8 ? 80 : 30} />
              <YAxis tick={{ fontSize: 11 }} width={64} />
              <Tooltip />
              {plan.valueKeys.length > 1 && <Legend />}
              {plan.valueKeys.map((k, i) => (
                <Bar key={k} dataKey={k} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
