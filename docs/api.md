# API reference

Base URL: `http://localhost:8000`. Interactive docs: `/docs` (Swagger) and `/redoc`.

Errors always have this shape:

```json
{ "error": { "code": "sql_rejected", "message": "…", "details": {} } }
```

| Code | HTTP | Meaning |
|---|---|---|
| `invalid_request` | 422 | request body failed schema validation; `details.fields` lists the fields |
| `bad_request` | 400 | invalid input rejected by a service |
| `not_found` | 404 | unknown table or history id |
| `sql_rejected` | 422 | SQL failed validation; `details.validation` lists the rules |
| `query_failed` | 400 | PostgreSQL rejected or failed the query |
| `query_timeout` | 408 | statement exceeded `STATEMENT_TIMEOUT_MS` |
| `database_unavailable` | 503 | cannot reach PostgreSQL |
| `llm_not_configured` | 503 | `GOOGLE_API_KEY` missing |
| `llm_auth_failed` / `llm_model_not_found` / `llm_rate_limited` / `llm_quota_exhausted` / `llm_timeout` / `llm_error` / `llm_invalid_output` | 502 / 502 / 429 / 429 / 504 / 502 / 502 | model provider problems |
| `llm_overloaded` | 503 | provider reported a temporary overload; the backend already retried twice (2 s, 5 s) |
| `embedding_error` / `vector_store_error` | 503 | embedding model or Chroma problems |
| `index_not_ready` | 409 | schema index is missing or still building |
| `internal_error` | 500 | unexpected failure (details are logged, not returned) |

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Component health: api, database, vector_index, llm |
| GET | `/api/settings` | Non-secret runtime configuration |
| GET | `/api/database/status` | Connection, server version, role, read-only flag |
| GET | `/api/schema` | Full discovered schema (tables, columns, keys, indexes, relationships) |
| GET | `/api/schema/status` | Index state and whether it matches the live schema |
| POST | `/api/schema/refresh` | Re-inspect; body `{"reindex": true}` rebuilds the vector index |
| GET | `/api/schema/tables/{name}` | One table, its retrieval document and relationships |
| POST | `/api/query/generate` | One-off question to SQL, no conversation context |
| POST | `/api/chat` | Question with conversation context; `conversation_id` optional |
| POST | `/api/query/validate` | Validate SQL without running it |
| POST | `/api/query/execute` | Validate again and run read-only SQL |
| GET | `/api/history` | Paged history, newest first (`limit`, `offset`) |
| GET | `/api/history/{id}` | One history entry |
| POST | `/api/evaluation/run` | Start the golden-set evaluation (202); body `{"mode": "full" \| "retrieval_only", "resume": false}` optional; `resume` keeps earlier answers that did not fail |
| GET | `/api/evaluation/results` | Run progress and the latest report |

## Examples

Ask a question:

```bash
curl -s -X POST localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"question": "Which 5 customers spent the most?"}'
```

Response fields: `history_id`, `conversation_id`, `question`, `standalone_question`, `status`, `sql`, `explanation`, `tables_used`, `assumptions`, `confidence`, `clarification_question`, `message`, `validation`, `retrieval` (hits, selected tables with source, join paths), `attempts`, `attempt_errors`, `latency`.

`status` is one of `ok`, `clarification_needed`, `cannot_answer`, `invalid_sql`.

Follow-up in the same conversation:

```bash
curl -s -X POST localhost:8000/api/chat -H 'content-type: application/json' \
  -d '{"question": "only for completed orders", "conversation_id": "<id from the previous response>"}'
```

Run SQL (rejected statements never reach the database):

```bash
curl -s -X POST localhost:8000/api/query/execute -H 'content-type: application/json' \
  -d '{"sql": "SELECT order_status, COUNT(*) AS n FROM orders GROUP BY order_status"}'
```

```json
{ "status": "success", "executed_sql": "…", "columns": ["order_status", "n"], "rows": [["<status>", <count>], …],
  "row_count": <rows returned>, "truncated": false, "max_rows": 1000, "execution_time_ms": <ms>, "history_id": null }
```
