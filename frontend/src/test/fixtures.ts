import type { ExecuteResponse, GenerateResponse } from "../types/api";

export function makeTurn(overrides: Partial<GenerateResponse> = {}): GenerateResponse {
  return {
    history_id: 1,
    conversation_id: "conv-1",
    question: "Top customers by spend",
    standalone_question: "Top customers by spend",
    status: "ok",
    sql: "SELECT c.first_name, SUM(o.total_amount) AS spend FROM customers c JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.first_name LIMIT 5",
    explanation: "Sums order totals per customer.",
    tables_used: ["customers", "orders"],
    assumptions: [],
    confidence: "high",
    clarification_question: null,
    message: null,
    validation: { valid: true, normalized_sql: null, statement_type: "select", dialect: "postgres", tables: ["customers", "orders"], errors: [], warnings: [] },
    retrieval: {
      query: "Top customers by spend",
      top_k: 10,
      embedding_model: "all-MiniLM-L6-v2",
      latency_ms: 12,
      hits: [{ doc_id: "table:orders", doc_type: "table", tables: ["orders"], score: 0.71, preview: "orders: customer purchases" }],
      semantic_tables: [{ name: "orders", score: 0.71, source: "semantic", reason: "top match" }],
      tables: [
        { name: "orders", score: 0.71, source: "semantic", reason: "top match" },
        { name: "customers", score: null, source: "expanded", reason: "parent of orders" },
      ],
      relationships: [{ child_table: "orders", child_columns: ["customer_id"], parent_table: "customers", parent_columns: ["customer_id"], cardinality: "one-to-many" }],
    },
    attempts: 1,
    attempt_errors: [],
    latency: { retrieval_ms: 12, generation_ms: 800, total_ms: 812 },
    ...overrides,
  };
}

export function makeResult(overrides: Partial<ExecuteResponse> = {}): ExecuteResponse {
  return {
    status: "success",
    executed_sql: "SELECT 1",
    columns: ["first_name", "spend"],
    rows: [
      ["Asha", 9000],
      ["Ravi", 7000],
      ["Meera", 5000],
    ],
    row_count: 3,
    truncated: false,
    max_rows: 1000,
    execution_time_ms: 4.2,
    history_id: 1,
    ...overrides,
  };
}
