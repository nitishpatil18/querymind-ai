import { Key, Link2, Table2 } from "lucide-react";
import { useState } from "react";
import { Alert, Badge, Card, CardHeader, Empty, PageHeader, Spinner } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { cn } from "../utils/format";

export function ExplorerPage() {
  const schema = useAsync(() => api.schema());
  const status = useAsync(() => api.databaseStatus());
  const [selected, setSelected] = useState<string | null>(null);
  const name = selected ?? schema.data?.tables[0]?.name ?? null;
  const table = schema.data?.tables.find((t) => t.name === name) ?? null;

  return (
    <div>
      <PageHeader title="Database Explorer" description="Live structure of the connected database, read directly from PostgreSQL metadata." />
      {status.data && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <Badge tone={status.data.connected ? "green" : "red"}>{status.data.connected ? "connected" : "disconnected"}</Badge>
          {status.data.database && <span className="text-slate-600">{status.data.database}</span>}
          {status.data.server_version && <span className="text-slate-400">PostgreSQL {status.data.server_version}</span>}
          {status.data.read_only && <Badge tone="indigo">read-only role</Badge>}
        </div>
      )}
      {schema.loading && !schema.data && <Spinner label="Reading schema…" />}
      {schema.error && <Alert kind="error" title="Could not read the schema">{schema.error.message}</Alert>}
      {schema.data && schema.data.tables.length === 0 && <Empty title="No tables found">The configured schemas contain no tables.</Empty>}
      {schema.data && table && (
        <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
          <nav aria-label="Tables" className="space-y-1">
            {schema.data.tables.map((t) => (
              <button
                key={t.name}
                type="button"
                onClick={() => setSelected(t.name)}
                aria-current={t.name === name}
                className={cn("flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm", t.name === name ? "bg-brand-50 font-medium text-brand-800" : "text-slate-700 hover:bg-slate-100")}
              >
                <span className="flex items-center gap-2">
                  <Table2 className="h-4 w-4" aria-hidden />
                  {t.name}
                </span>
                <span className="text-xs text-slate-400">{t.columns.length}</span>
              </button>
            ))}
          </nav>

          <div className="space-y-4">
            <Card>
              <CardHeader title={table.name} subtitle={table.comment ?? undefined} />
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-2 font-medium">Column</th>
                      <th className="px-4 py-2 font-medium">Type</th>
                      <th className="px-4 py-2 font-medium">Constraints</th>
                      <th className="px-4 py-2 font-medium">Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {table.columns.map((c) => (
                      <tr key={c.name}>
                        <td className="whitespace-nowrap px-4 py-2 font-mono text-[13px]">
                          <span className="inline-flex items-center gap-1.5">
                            {c.primary_key && <Key className="h-3.5 w-3.5 text-amber-600" aria-label="primary key" />}
                            {c.foreign_key && <Link2 className="h-3.5 w-3.5 text-sky-600" aria-label="foreign key" />}
                            {c.name}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-4 py-2 text-slate-600">{c.type}</td>
                        <td className="px-4 py-2">
                          <div className="flex flex-wrap gap-1">
                            {!c.nullable && <Badge>not null</Badge>}
                            {c.unique && <Badge>unique</Badge>}
                            {c.default && <Badge title="default">default {c.default}</Badge>}
                            {c.allowed_values.length > 0 && <Badge tone="indigo" title={c.allowed_values.join(", ")}>{c.allowed_values.length} allowed values</Badge>}
                          </div>
                        </td>
                        <td className="px-4 py-2 text-slate-600">{c.comment ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            {table.foreign_keys.length > 0 && (
              <Card>
                <CardHeader title="Foreign keys" />
                <ul className="divide-y divide-slate-100 text-sm">
                  {table.foreign_keys.map((fk, i) => (
                    <li key={i} className="px-4 py-2 font-mono text-[13px]">
                      {fk.columns.join(", ")} → {fk.referred_table}.{fk.referred_columns.join(", ")}
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {table.indexes.length > 0 && (
              <Card>
                <CardHeader title="Indexes" />
                <ul className="divide-y divide-slate-100 text-sm">
                  {table.indexes.map((ix) => (
                    <li key={ix.name} className="flex flex-wrap items-center gap-2 px-4 py-2">
                      <span className="font-mono text-[13px]">{ix.name}</span>
                      <span className="text-slate-500">({ix.columns.join(", ")})</span>
                      {ix.unique && <Badge>unique</Badge>}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
