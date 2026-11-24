import { Alert, Badge, Card, CardHeader, PageHeader, Spinner, StatusDot } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

export function SettingsPage() {
  const settings = useAsync(() => api.settings());
  const health = useAsync(() => api.health());
  const s = settings.data;

  return (
    <div>
      <PageHeader title="Settings" description="Runtime configuration reported by the backend. Values come from environment variables; secrets are never shown." />
      {settings.loading && !s && <Spinner />}
      {settings.error && <Alert kind="error" title="Could not load settings">{settings.error.message}</Alert>}
      {s && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader title="Language model" />
            <Rows
              rows={[
                ["Provider", s.llm_provider],
                ["Model", s.llm_model],
                ["API key", <Badge key="k" tone={s.llm_api_key_configured ? "green" : "red"}>{s.llm_api_key_configured ? "configured" : "missing"}</Badge>],
                ["Max generation attempts", s.generation_max_attempts],
                ["Conversation context turns", s.conversation_context_turns],
              ]}
            />
          </Card>
          <Card>
            <CardHeader title="Retrieval" />
            <Rows
              rows={[
                ["Embedding provider", s.embedding_provider],
                ["Embedding model", s.embedding_model],
                ["Top-K documents", s.retrieval_top_k],
                ["Max tables in context", s.retrieval_max_tables],
                ["Indexed schemas", s.allowed_schemas.join(", ")],
              ]}
            />
          </Card>
          <Card>
            <CardHeader title="Execution safety" />
            <Rows
              rows={[
                ["Max result rows", s.max_result_rows.toLocaleString()],
                ["Statement timeout", `${s.statement_timeout_ms / 1000} s`],
                ["Environment", s.app_env],
              ]}
            />
          </Card>
          <Card>
            <CardHeader title="Service health" />
            {health.data ? (
              <ul className="divide-y divide-slate-100 text-sm">
                {Object.entries(health.data.components).map(([name, c]) => (
                  <li key={name} className="flex items-center justify-between gap-3 px-4 py-2.5">
                    <span className="flex items-center gap-2 font-medium capitalize">
                      <StatusDot status={c.status} />
                      {name.replace("_", " ")}
                    </span>
                    <span className="truncate text-xs text-slate-500">{c.detail ?? c.status}</span>
                  </li>
                ))}
              </ul>
            ) : health.error ? (
              <div className="p-4">
                <Alert kind="error">{health.error.message}</Alert>
              </div>
            ) : (
              <div className="p-4">
                <Spinner />
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

function Rows({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="divide-y divide-slate-100 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-center justify-between gap-3 px-4 py-2.5">
          <dt className="text-slate-500">{k}</dt>
          <dd className="text-right font-medium text-slate-900">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
