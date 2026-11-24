import { Badge } from "./ui";
import type { RetrievalDebug } from "../types/api";
import { formatMs } from "../utils/format";

export function RetrievalPanel({ retrieval }: { retrieval: RetrievalDebug }) {
  return (
    <div className="space-y-4 p-4 text-sm">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
        <span>Embedding model: {retrieval.embedding_model ?? "n/a"}</span>
        <span>Top-K: {retrieval.top_k}</span>
        <span>Retrieval time: {formatMs(retrieval.latency_ms)}</span>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Tables sent to the model</h3>
        <ul className="space-y-1.5">
          {retrieval.tables.map((t) => (
            <li key={t.name} className="flex flex-wrap items-center gap-2">
              <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{t.name}</code>
              <Badge tone={t.source === "semantic" ? "indigo" : "sky"}>{t.source === "semantic" ? "semantic match" : "added via foreign key"}</Badge>
              {t.score !== null && <span className="text-xs text-slate-500">similarity {t.score.toFixed(3)}</span>}
              <span className="text-xs text-slate-500">{t.reason}</span>
            </li>
          ))}
        </ul>
      </div>

      {retrieval.relationships.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Join paths included</h3>
          <ul className="space-y-1 font-mono text-xs text-slate-700">
            {retrieval.relationships.map((r) => (
              <li key={`${r.child_table}.${r.child_columns.join()}`}>
                {r.child_table}.{r.child_columns.join(", ")} → {r.parent_table}.{r.parent_columns.join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Top retrieved documents</h3>
        <ul className="space-y-2">
          {retrieval.hits.map((h) => (
            <li key={h.doc_id} className="rounded-lg border border-slate-200 p-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <code className="text-xs font-medium">{h.doc_id}</code>
                <Badge>{h.doc_type}</Badge>
                <span className="text-xs text-slate-500">score {h.score.toFixed(3)}</span>
              </div>
              <p className="mt-1 line-clamp-2 whitespace-pre-line text-xs text-slate-600">{h.preview}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
