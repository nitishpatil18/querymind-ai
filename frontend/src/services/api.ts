import type {
  DatabaseStatus,
  EvalProgress,
  EvalResults,
  ExecuteResponse,
  GenerateResponse,
  HealthResponse,
  HistoryItem,
  HistoryPage,
  RuntimeSettings,
  SchemaInfo,
  SchemaStatus,
  TableDetail,
  ValidationResult,
} from "../types/api";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(message: string, status: number, code = "error", details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Cannot reach the QueryMind backend. Check that it is running.", 0, "network_error");
  }
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON error page from a proxy */
  }
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null)?.error;
    throw new ApiError(err?.message ?? `Request failed (${res.status}).`, res.status, err?.code ?? "http_error", err?.details ?? {});
  }
  return body as T;
}

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const api = {
  health: () => request<HealthResponse>("/health"),
  settings: () => request<RuntimeSettings>("/api/settings"),
  databaseStatus: () => request<DatabaseStatus>("/api/database/status"),
  schema: () => request<SchemaInfo>("/api/schema"),
  schemaStatus: () => request<SchemaStatus>("/api/schema/status"),
  refreshSchema: (reindex: boolean) => post<SchemaStatus>("/api/schema/refresh", { reindex }),
  table: (name: string) => request<TableDetail>(`/api/schema/tables/${encodeURIComponent(name)}`),
  chat: (body: { question: string; conversation_id?: string | null; regenerate_of?: number | null }) =>
    post<GenerateResponse>("/api/chat", body),
  validate: (sql: string) => post<ValidationResult>("/api/query/validate", { sql }),
  execute: (body: { sql: string; history_id?: number | null }) => post<ExecuteResponse>("/api/query/execute", body),
  history: (limit = 25, offset = 0) => request<HistoryPage>(`/api/history?limit=${limit}&offset=${offset}`),
  historyItem: (id: number) => request<HistoryItem>(`/api/history/${id}`),
  runEvaluation: (mode?: "full" | "retrieval_only", resume = false) =>
    post<EvalProgress>("/api/evaluation/run", { ...(mode ? { mode } : {}), ...(resume ? { resume: true } : {}) }),
  evaluationResults: () => request<EvalResults>("/api/evaluation/results"),
};

export type Api = typeof api;
