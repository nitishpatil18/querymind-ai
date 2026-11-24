import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, CardHeader, Empty, MetricCard, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { ApiError, api } from "../services/api";
import type { EvalReport, QuestionResult } from "../types/api";
import { cn, formatDateTime, formatMs, formatPct } from "../utils/format";

type M = EvalReport["metrics"];

function pct(m: M, key: string, hintWhenMissing = "needs LLM run") {
  const v = m[key];
  return v === undefined || v === null ? { value: "n/a", hint: hintWhenMissing } : { value: formatPct(v), hint: undefined };
}

function resultBadge(r: QuestionResult) {
  if (r.status === "error") return <Badge tone="red">error</Badge>;
  if (r.execution_match === true) return <Badge tone="green">correct</Badge>;
  if (r.execution_match === false) return <Badge tone="red">wrong result</Badge>;
  if (r.behavior_ok === true) return <Badge tone="green">handled</Badge>;
  if (r.behavior_ok === false) return <Badge tone="red">mishandled</Badge>;
  if (r.status === null) return <Badge>retrieval only</Badge>;
  return <Badge>{r.status}</Badge>;
}

export function EvaluationPage() {
  const [polling, setPolling] = useState<number | null>(null);
  const { data, error, loading, reload } = useAsync(() => api.evaluationResults(), [], polling);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "failed">("all");
  const running = data?.progress.status === "running";
  const status = data?.progress.status;

  // poll while a run is in progress, stop afterwards
  useEffect(() => {
    if (status === "running") setPolling(1500);
    else if (status) setPolling(null);
  }, [status]);

  async function start(mode?: "full" | "retrieval_only", resume = false) {
    setStarting(true);
    setStartError(null);
    try {
      await api.runEvaluation(mode, resume);
      reload();
    } catch (e) {
      setStartError(e instanceof ApiError ? e.message : "Could not start the evaluation.");
    } finally {
      setStarting(false);
    }
  }

  const report = data?.report ?? null;
  const progress = data?.progress;
  const m = report?.metrics ?? {};
  const unfinished = Number(m.questions_with_errors ?? 0);
  const canResume = report?.mode === "full" && unfinished > 0;
  const rows = report ? (filter === "failed" ? report.results.filter((r) => r.execution_match === false || r.behavior_ok === false || r.status === "error") : report.results) : [];

  return (
    <div>
      <PageHeader
        title="Evaluation"
        description="Runs the golden question set against the live pipeline. Every number below is measured by the backend; nothing is precomputed."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void start("retrieval_only")} disabled={starting || running}>
              Retrieval only
            </Button>
            {canResume && (
              <Button onClick={() => void start("full", true)} disabled={starting || running}>
                Resume ({unfinished} unfinished)
              </Button>
            )}
            <Button variant="primary" onClick={() => void start()} loading={starting || running} icon={<Play className="h-4 w-4" />}>
              {running ? "Running…" : "Run evaluation"}
            </Button>
          </div>
        }
      />
      {loading && !data && <Spinner label="Loading results…" />}
      {error && <Alert kind="error" title="Could not load results">{error.message}</Alert>}
      {startError && <Alert kind="error" title="Evaluation not started">{startError}</Alert>}
      {progress?.status === "failed" && <Alert kind="error" title="The last run failed">{progress.error}</Alert>}

      {running && progress && (
        <Card className="mb-4 p-4">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Evaluating{progress.current ? ` ${progress.current}` : ""}…</span>
            <span className="text-slate-500">
              {progress.completed} / {progress.total}
            </span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.completed}>
            <div className="h-full bg-brand-600 transition-all" style={{ width: `${progress.total ? (progress.completed / progress.total) * 100 : 0}%` }} />
          </div>
        </Card>
      )}

      {!loading && !report && !running && <Empty title="No evaluation has been run">Run the evaluation to measure accuracy on this database.</Empty>}

      {report && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <Badge tone={report.mode === "full" ? "green" : "amber"}>{report.mode === "full" ? "full pipeline" : "retrieval only"}</Badge>
            <span>{formatDateTime(report.finished_at)}</span>
            <span>·</span>
            <span>
              LLM: {report.llm_model ? `${report.llm_provider} / ${report.llm_model}` : "not used"}
            </span>
            <span>·</span>
            <span>
              Embeddings: {report.embedding_provider} / {report.embedding_model}
            </span>
            <span>·</span>
            <span>
              top-k {report.retrieval_top_k}, max {report.retrieval_max_tables} tables
            </span>
            {m.questions_evaluated != null && (
              <>
                <span>·</span>
                <span className={m.questions_evaluated < (m.questions_total ?? 0) ? "font-medium text-amber-700" : undefined}>
                  {m.questions_evaluated} of {m.questions_total} questions evaluated
                </span>
              </>
            )}
          </div>
          {report.notes.map((n) => (
            <Alert key={n} kind="warning">
              {n}
            </Alert>
          ))}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Execution accuracy" {...pct(m, "execution_accuracy")} hint={pct(m, "execution_accuracy").hint ?? `${m.questions_strict_scored ?? 0} strictly scored`} />
            <MetricCard label="Accuracy, extra columns allowed" {...pct(m, "execution_accuracy_extra_columns_allowed")} hint={pct(m, "execution_accuracy_extra_columns_allowed").hint ?? "same data, unrequested columns ignored"} />
            <MetricCard label="SQL validity" {...pct(m, "sql_validity_rate")} />
            <MetricCard label="Execution success" {...pct(m, "execution_success_rate")} />
            <MetricCard label="Exact SQL match" {...pct(m, "exact_sql_match_rate")} hint="informational; formatting-sensitive" />
            <MetricCard label="Recall@K (semantic)" {...pct(m, "recall_at_k_semantic", "")} />
            <MetricCard label="Recall after FK expansion" {...pct(m, "recall_after_expansion", "")} />
            <MetricCard label="Precision@K (semantic)" {...pct(m, "precision_at_k_semantic", "")} />
            <MetricCard label="Avg generation latency" value={m.avg_generation_latency_ms == null ? "n/a" : formatMs(m.avg_generation_latency_ms)} hint={m.avg_generation_latency_ms == null ? "needs LLM run" : undefined} />
            <MetricCard label="Unsafe SQL rejected (validator)" {...pct(m, "invalid_query_rejection_rate_validator", "")} hint={`${m.adversarial_cases ?? 0} adversarial cases`} />
            <MetricCard label="Unsafe SQL blocked end to end" {...pct(m, "invalid_query_blocked_end_to_end", "")} />
            <MetricCard label="Refusals correct" {...pct(m, "refusal_correct_rate")} />
            <MetricCard label="Ambiguity handled" {...pct(m, "ambiguity_handled_rate")} />
          </div>

          <Card>
            <CardHeader title="By category" />
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">Category</th>
                    <th className="px-4 py-2 font-medium">Questions</th>
                    <th className="px-4 py-2 font-medium">Execution accuracy</th>
                    <th className="px-4 py-2 font-medium">Errors</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {Object.entries(report.by_category).map(([cat, e]) => (
                    <tr key={cat}>
                      <td className="px-4 py-2">{cat}</td>
                      <td className="px-4 py-2">{e.questions}</td>
                      <td className="px-4 py-2">{e.execution_accuracy === undefined || e.execution_accuracy === null ? "n/a" : formatPct(e.execution_accuracy)}</td>
                      <td className="px-4 py-2">{e.errors ?? "n/a"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Per-question results"
              actions={
                <div role="group" aria-label="Filter" className="inline-flex rounded-lg bg-slate-100 p-0.5 text-xs">
                  {(["all", "failed"] as const).map((f) => (
                    <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)} className={cn("rounded-md px-2.5 py-1 font-medium capitalize", filter === f ? "bg-white shadow-sm" : "text-slate-500")}>
                      {f}
                    </button>
                  ))}
                </div>
              }
            />
            <div className="max-h-[32rem] overflow-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-2 font-medium">ID</th>
                    <th className="px-4 py-2 font-medium">Question</th>
                    <th className="px-4 py-2 font-medium">Outcome</th>
                    <th className="px-4 py-2 font-medium">Recall@K</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((r) => (
                    <tr key={r.id} className="align-top">
                      <td className="whitespace-nowrap px-4 py-2 font-mono text-xs">{r.id}</td>
                      <td className="px-4 py-2">
                        {r.question}
                        {r.error && <p className="mt-0.5 text-xs text-red-600">{r.error}</p>}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2">{resultBadge(r)}</td>
                      <td className="whitespace-nowrap px-4 py-2">{r.recall_at_k === null ? "n/a" : formatPct(r.recall_at_k, 0)}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                        No failing questions.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <CardHeader title="Adversarial SQL" subtitle="Statements that must never reach the database" />
            <ul className="divide-y divide-slate-100 text-sm">
              {report.adversarial.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                  <div className="min-w-0">
                    <code className="block max-w-xl truncate text-xs text-slate-700">{a.sql}</code>
                    <span className="text-xs text-slate-500">{a.why}</span>
                  </div>
                  <Badge tone={a.rejected_by_validator && a.blocked_end_to_end ? "green" : "red"}>{a.rejected_by_validator ? (a.rule ?? "rejected") : "NOT REJECTED"}</Badge>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}
