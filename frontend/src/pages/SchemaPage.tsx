import { DatabaseZap, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Alert, Badge, Button, Card, CardHeader, MetricCard, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { ApiError, api } from "../services/api";
import { formatDateTime, formatMs } from "../utils/format";

export function SchemaPage() {
  const { data, error, loading, reload } = useAsync(() => api.schemaStatus(), [], 3000);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function refresh(reindex: boolean) {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      await api.refreshSchema(reindex);
      setNotice(reindex ? "Schema re-inspected and the vector index rebuilt." : "Schema re-inspected.");
      reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  }

  const idx = data?.index;
  return (
    <div>
      <PageHeader
        title="Schema Management"
        description="The retrieval index is built from the live database. Rebuild it after the structure changes; it also rebuilds automatically when a change is detected at startup."
        actions={
          <div className="flex gap-2">
            <Button onClick={() => void refresh(false)} disabled={busy} icon={<RefreshCw className="h-4 w-4" />}>
              Re-inspect schema
            </Button>
            <Button variant="primary" onClick={() => void refresh(true)} loading={busy} icon={<DatabaseZap className="h-4 w-4" />}>
              Rebuild index
            </Button>
          </div>
        }
      />
      {loading && !data && <Spinner label="Loading index status…" />}
      {error && <Alert kind="error" title="Could not load status">{error.message}</Alert>}
      {actionError && <Alert kind="error" title="Action failed">{actionError}</Alert>}
      {notice && <Alert kind="success">{notice}</Alert>}

      {data && idx && (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Tables discovered" value={data.tables_discovered} />
            <MetricCard label="Documents indexed" value={idx.documents_indexed} hint={`${data.vector_documents} in vector store`} />
            <MetricCard label="Last indexed" value={<span className="text-base">{formatDateTime(idx.last_indexed_at)}</span>} hint={idx.duration_ms !== null ? `took ${formatMs(idx.duration_ms)}` : undefined} />
            <MetricCard
              label="Index state"
              value={<span className="text-base capitalize">{idx.status.replace("_", " ")}</span>}
              tone={idx.status === "ready" && data.index_is_current ? "green" : idx.status === "failed" ? "red" : "slate"}
              hint={data.index_is_current ? "matches the live schema" : "out of date with the live schema"}
            />
          </div>
          {!data.index_is_current && idx.status === "ready" && (
            <Alert kind="warning" title="The index is out of date">
              The database structure changed since the last index. Rebuild it so retrieval sees the new tables and columns.
            </Alert>
          )}
          {idx.status === "not_indexed" && <Alert kind="warning" title="Nothing is indexed yet">Rebuild the index before asking questions.</Alert>}
          {idx.error && <Alert kind="error" title="Last indexing failed">{idx.error}</Alert>}
          <Card>
            <CardHeader title="Details" />
            <dl className="grid gap-x-6 gap-y-3 px-4 py-3 text-sm sm:grid-cols-2">
              <Detail label="Database" value={data.database ?? "n/a"} />
              <Detail label="Embedding model" value={idx.embedding_model ? `${idx.embedding_provider} / ${idx.embedding_model}` : "n/a"} />
              <Detail label="Schema inspected" value={formatDateTime(data.inspected_at)} />
              <Detail label="Schema fingerprint" value={<code className="text-xs">{data.schema_fingerprint?.slice(0, 16) ?? "n/a"}</code>} />
              <Detail label="Indexed fingerprint" value={<code className="text-xs">{idx.schema_fingerprint?.slice(0, 16) ?? "n/a"}</code>} />
              <Detail label="Current" value={<Badge tone={data.index_is_current ? "green" : "amber"}>{data.index_is_current ? "yes" : "no"}</Badge>} />
            </dl>
          </Card>
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-slate-900">{value}</dd>
    </div>
  );
}
