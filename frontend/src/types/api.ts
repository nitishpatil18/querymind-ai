// Types mirroring the backend's Pydantic response models.

export interface ValidationIssue {
  code: string;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  normalized_sql: string | null;
  statement_type: string | null;
  dialect: string;
  tables: string[];
  errors: ValidationIssue[];
  warnings: string[];
}

export interface RetrievalHit {
  doc_id: string;
  doc_type: string;
  tables: string[];
  score: number;
  preview: string;
}

export interface RetrievedTable {
  name: string;
  score: number | null;
  source: "semantic" | "expanded";
  reason: string;
}

export interface Relationship {
  child_table: string;
  child_columns: string[];
  parent_table: string;
  parent_columns: string[];
  cardinality: string;
}

export interface RetrievalDebug {
  query: string;
  top_k: number;
  embedding_model: string | null;
  latency_ms: number;
  hits: RetrievalHit[];
  semantic_tables: RetrievedTable[];
  tables: RetrievedTable[];
  relationships: Relationship[];
}

export type GenerationStatus = "ok" | "clarification_needed" | "cannot_answer" | "invalid_sql";

export interface GenerateResponse {
  history_id: number;
  conversation_id: string;
  question: string;
  standalone_question: string;
  status: GenerationStatus;
  sql: string | null;
  explanation: string;
  tables_used: string[];
  assumptions: string[];
  confidence: "high" | "medium" | "low" | null;
  clarification_question: string | null;
  message: string | null;
  validation: ValidationResult | null;
  retrieval: RetrievalDebug | null;
  attempts: number;
  attempt_errors: string[];
  latency: { retrieval_ms: number; generation_ms: number; total_ms: number };
}

export type CellValue = string | number | boolean | null;

export interface ExecuteResponse {
  status: string;
  executed_sql: string;
  columns: string[];
  rows: CellValue[][];
  row_count: number;
  truncated: boolean;
  max_rows: number;
  execution_time_ms: number;
  history_id: number | null;
}

export interface HistoryItem {
  id: number;
  conversation_id: string;
  created_at: string;
  question: string;
  standalone_question: string | null;
  status: string;
  sql: string | null;
  explanation: string | null;
  clarification_question: string | null;
  tables_used: string[];
  assumptions: string[];
  confidence: string | null;
  validation_valid: boolean | null;
  generation_ms: number | null;
  execution_status: string | null;
  row_count: number | null;
  execution_ms: number | null;
  execution_error: string | null;
  executed_at: string | null;
}

export interface HistoryPage {
  items: HistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DatabaseStatus {
  connected: boolean;
  database: string | null;
  server_version: string | null;
  user: string | null;
  read_only: boolean | null;
  schemas: string[];
  latency_ms: number | null;
  error: string | null;
}

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
  comment: string | null;
  primary_key: boolean;
  foreign_key: boolean;
  unique: boolean;
  allowed_values: string[];
}

export interface ForeignKeyInfo {
  name: string | null;
  columns: string[];
  referred_schema: string | null;
  referred_table: string;
  referred_columns: string[];
}

export interface TableInfo {
  schema_name: string;
  name: string;
  comment: string | null;
  columns: ColumnInfo[];
  primary_key: string[];
  foreign_keys: ForeignKeyInfo[];
  indexes: { name: string; columns: string[]; unique: boolean }[];
  constraints: { name: string | null; kind: string; columns: string[]; definition: string | null }[];
}

export interface SchemaInfo {
  database: string;
  schemas: string[];
  available_schemas: string[];
  tables: TableInfo[];
  relationships: Relationship[];
  inspected_at: string;
  fingerprint: string;
}

export interface TableDetail {
  table: TableInfo;
  document: string;
  relationships: Relationship[];
}

export interface IndexState {
  status: "not_indexed" | "indexing" | "ready" | "failed";
  last_indexed_at: string | null;
  tables_indexed: number;
  documents_indexed: number;
  schema_fingerprint: string | null;
  embedding_provider: string | null;
  embedding_model: string | null;
  duration_ms: number | null;
  error: string | null;
}

export interface SchemaStatus {
  index: IndexState;
  database: string | null;
  tables_discovered: number;
  schema_fingerprint: string | null;
  inspected_at: string | null;
  index_is_current: boolean;
  vector_documents: number;
}

export interface ComponentHealth {
  status: "ok" | "degraded" | "down";
  detail: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "down";
  components: Record<string, ComponentHealth>;
  version: string;
}

export interface RuntimeSettings {
  app_env: string;
  llm_provider: string;
  llm_model: string;
  llm_api_key_configured: boolean;
  embedding_provider: string;
  embedding_model: string;
  retrieval_top_k: number;
  retrieval_max_tables: number;
  max_result_rows: number;
  statement_timeout_ms: number;
  generation_max_attempts: number;
  conversation_context_turns: number;
  allowed_schemas: string[];
}

export interface QuestionResult {
  id: string;
  category: string;
  question: string;
  expected_behavior: string;
  status: string | null;
  generated_sql: string | null;
  sql_valid: boolean | null;
  executed: boolean | null;
  execution_match: boolean | null;
  llm_model?: string | null;
  execution_match_extra_columns: boolean | null;
  exact_sql_match: boolean | null;
  behavior_ok: boolean | null;
  retrieved_tables: string[];
  semantic_tables: string[];
  recall_at_k: number | null;
  precision_at_k: number | null;
  recall_expanded: number | null;
  precision_expanded: number | null;
  generation_ms: number | null;
  execution_ms: number | null;
  error: string | null;
}

export interface AdversarialResult {
  id: string;
  sql: string;
  why: string;
  rejected_by_validator: boolean;
  blocked_end_to_end: boolean;
  rule: string | null;
}

export interface EvalReport {
  run_id: string;
  mode: "full" | "retrieval_only";
  started_at: string;
  finished_at: string;
  llm_provider: string | null;
  llm_model: string | null;
  embedding_provider: string;
  embedding_model: string;
  retrieval_top_k: number;
  retrieval_max_tables: number;
  dataset_version: number;
  metrics: Record<string, number | null | undefined>;
  by_category: Record<string, { questions: number; errors?: number; execution_accuracy?: number | null; valid_sql?: number; behavior_ok?: number }>;
  results: QuestionResult[];
  adversarial: AdversarialResult[];
  golden_sql_check: { queries: number; valid: number; executed: number; failures: string[] };
  notes: string[];
}

export interface EvalProgress {
  status: "idle" | "running" | "completed" | "failed";
  started_at: string | null;
  completed: number;
  total: number;
  current: string | null;
  error: string | null;
  mode: string | null;
}

export interface EvalResults {
  progress: EvalProgress;
  report: EvalReport | null;
}
