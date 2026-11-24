import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { SqlViewer } from "../components/SqlViewer";
import { Alert, Badge, Button, Card, Empty, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { formatDateTime, formatMs } from "../utils/format";

const PAGE = 20;

export function HistoryPage() {
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const navigate = useNavigate();
  const { data, error, loading, reload } = useAsync(() => api.history(PAGE, offset), [offset]);

  return (
    <div>
      <PageHeader title="Query History" description="Every question asked, the SQL produced and how it ran." actions={<Button onClick={reload}>Refresh</Button>} />
      {loading && !data && <Spinner label="Loading history…" />}
      {error && <Alert kind="error" title="Could not load history">{error.message}</Alert>}
      {data && data.items.length === 0 && <Empty title="No queries yet">Ask a question on the New Query page and it will show up here.</Empty>}
      {data && data.items.length > 0 && (
        <>
          <ul className="space-y-2">
            {data.items.map((h) => (
              <li key={h.id}>
                <Card>
                  <button type="button" aria-expanded={open === h.id} onClick={() => setOpen(open === h.id ? null : h.id)} className="flex w-full flex-wrap items-center justify-between gap-2 px-4 py-3 text-left">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">{h.question}</p>
                      <p className="text-xs text-slate-500">{formatDateTime(h.created_at)}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={h.status === "ok" ? "green" : h.status === "invalid_sql" ? "red" : "amber"}>{h.status}</Badge>
                      {h.execution_status && (
                        <Badge tone={h.execution_status === "success" ? "green" : "red"}>
                          {h.execution_status === "success" ? `${h.row_count ?? 0} rows` : "execution failed"}
                        </Badge>
                      )}
                    </div>
                  </button>
                  {open === h.id && (
                    <div className="space-y-3 border-t border-slate-100 px-4 py-3">
                      {h.sql ? <SqlViewer sql={h.sql} /> : <p className="text-sm text-slate-500">{h.clarification_question ?? "No SQL was produced."}</p>}
                      {h.explanation && <p className="text-sm text-slate-700">{h.explanation}</p>}
                      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
                        {h.confidence && <span>Confidence: {h.confidence}</span>}
                        <span>Generation: {formatMs(h.generation_ms)}</span>
                        {h.execution_ms !== null && <span>Execution: {formatMs(h.execution_ms)}</span>}
                        {h.tables_used.length > 0 && <span>Tables: {h.tables_used.join(", ")}</span>}
                      </div>
                      {h.execution_error && <Alert kind="error">{h.execution_error}</Alert>}
                      <Button icon={<RotateCcw className="h-4 w-4" />} onClick={() => navigate("/", { state: { question: h.question } })}>
                        Ask again
                      </Button>
                    </div>
                  )}
                </Card>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-between text-sm text-slate-600">
            <span>
              {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
            </span>
            <div className="flex gap-2">
              <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Previous
              </Button>
              <Button disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
