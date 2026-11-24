import { BarChart3, ChevronDown, Play, RefreshCw, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError, api } from "../services/api";
import type { ExecuteResponse, GenerateResponse } from "../types/api";
import { recommendChart } from "../utils/charts";
import { formatMs } from "../utils/format";
import { ChartPanel } from "./ChartPanel";
import { ResultsTable } from "./ResultsTable";
import { RetrievalPanel } from "./RetrievalPanel";
import { SqlViewer } from "./SqlViewer";
import { Alert, Badge, Button, Card } from "./ui";

function Collapsible({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-slate-100">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium text-slate-700 hover:bg-slate-50">
        {title}
        <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {open && children}
    </div>
  );
}

const CONFIDENCE_TONE = { high: "green", medium: "amber", low: "red" } as const;

export function TurnCard({ turn, onRegenerate, busy }: { turn: GenerateResponse; onRegenerate: (turn: GenerateResponse) => void; busy: boolean }) {
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ExecuteResponse | null>(null);
  const [execError, setExecError] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "chart">("table");

  const plan = useMemo(() => (result ? recommendChart(result.columns, result.rows) : null), [result]);
  const canRun = turn.status === "ok" && !!turn.sql && turn.validation?.valid === true;

  async function run() {
    if (!turn.sql) return;
    setExecuting(true);
    setExecError(null);
    try {
      const res = await api.execute({ sql: turn.sql, history_id: turn.history_id });
      setResult(res);
      setView("table");
    } catch (e) {
      setResult(null);
      setExecError(e instanceof ApiError ? e.message : "Execution failed.");
    } finally {
      setExecuting(false);
    }
  }

  return (
    <Card>
      <div className="px-4 py-3">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Question</p>
        <p className="mt-0.5 text-sm font-medium text-slate-900">{turn.question}</p>
        {turn.standalone_question && turn.standalone_question !== turn.question && (
          <p className="mt-1 text-xs text-slate-500">Interpreted as: {turn.standalone_question}</p>
        )}
      </div>

      <div className="space-y-3 border-t border-slate-100 px-4 py-3">
        {turn.status === "clarification_needed" && (
          <Alert kind="info" title="I need a bit more detail">
            {turn.clarification_question ?? turn.message}
          </Alert>
        )}
        {turn.status === "cannot_answer" && (
          <Alert kind="warning" title="This can't be answered from the database">
            {turn.message ?? turn.explanation}
          </Alert>
        )}
        {turn.status === "invalid_sql" && (
          <Alert kind="error" title="No safe SQL could be produced">
            {turn.message ?? "The generated query failed validation."}
            {turn.validation && turn.validation.errors.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {turn.validation.errors.map((e, i) => (
                  <li key={i}>{e.message}</li>
                ))}
              </ul>
            )}
          </Alert>
        )}

        {turn.sql && (
          <>
            <SqlViewer sql={turn.validation?.normalized_sql ?? turn.sql} />
            <div className="flex flex-wrap items-center gap-2">
              {turn.confidence && <Badge tone={CONFIDENCE_TONE[turn.confidence]}>{turn.confidence} confidence</Badge>}
              {turn.validation && <Badge tone={turn.validation.valid ? "green" : "red"}>{turn.validation.valid ? "validated read-only" : "failed validation"}</Badge>}
              {turn.tables_used.map((t) => (
                <Badge key={t} tone="indigo">
                  {t}
                </Badge>
              ))}
              <span className="text-xs text-slate-400">generated in {formatMs(turn.latency.total_ms)}</span>
              {turn.attempts > 1 && <span className="text-xs text-slate-400">{turn.attempts} attempts</span>}
            </div>
          </>
        )}

        {turn.explanation && turn.status === "ok" && <p className="text-sm text-slate-700">{turn.explanation}</p>}

        {turn.assumptions.length > 0 && (
          <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
            <p className="font-medium">Assumptions</p>
            <ul className="mt-0.5 list-disc pl-5">
              {turn.assumptions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {canRun && (
            <Button variant="primary" onClick={run} loading={executing} icon={<Play className="h-4 w-4" />}>
              Run query
            </Button>
          )}
          <Button onClick={() => onRegenerate(turn)} disabled={busy} icon={<RefreshCw className="h-4 w-4" />}>
            Regenerate
          </Button>
        </div>

        {execError && <Alert kind="error" title="Query failed">{execError}</Alert>}
      </div>

      {result && (
        <div className="border-t border-slate-100">
          <div className="flex items-center gap-1 px-4 pt-3">
            <div role="tablist" aria-label="Result view" className="inline-flex rounded-lg bg-slate-100 p-0.5 text-sm">
              <button role="tab" aria-selected={view === "table"} type="button" onClick={() => setView("table")} className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1 font-medium ${view === "table" ? "bg-white shadow-sm" : "text-slate-500"}`}>
                <Table2 className="h-4 w-4" aria-hidden /> Table
              </button>
              <button
                role="tab"
                aria-selected={view === "chart"}
                type="button"
                disabled={!plan}
                title={plan ? undefined : "This result has no numeric series to chart"}
                onClick={() => setView("chart")}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1 font-medium disabled:cursor-not-allowed disabled:text-slate-300 ${view === "chart" ? "bg-white shadow-sm" : "text-slate-500"}`}
              >
                <BarChart3 className="h-4 w-4" aria-hidden /> Chart
              </button>
            </div>
          </div>
          {view === "chart" && plan ? <ChartPanel plan={plan} /> : <ResultsTable result={result} />}
        </div>
      )}

      {turn.retrieval && (
        <Collapsible title="Retrieved schema context">
          <RetrievalPanel retrieval={turn.retrieval} />
        </Collapsible>
      )}
      {turn.attempt_errors.length > 0 && (
        <Collapsible title={`Repair attempts (${turn.attempt_errors.length})`}>
          <ul className="list-disc space-y-1 px-8 py-3 text-xs text-slate-600">
            {turn.attempt_errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </Collapsible>
      )}
    </Card>
  );
}
