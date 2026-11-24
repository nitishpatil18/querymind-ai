# Project status

Legend: **Verified** = exercised by an automated test or a command that was actually run (development environment, then Docker on a MacBook with a real Gemini key). Nothing below is marked verified without having been run.

## Phases

| # | Phase | Status | Evidence |
|---|---|---|---|
| 1 | PostgreSQL demo database | Done, verified | 6 tables, 520 customers, 12 categories, 120 products, 1650 orders, 3386 order items, 1727 payments; deterministic seed; read-only role; integration tests |
| 2 | Dynamic schema inspection | Done, verified | `SchemaInspector` tests: tables, columns, PK, FK, indexes, comments, CHECK allowed values, fingerprint |
| 3 | Schema RAG (ChromaDB + embeddings) | Done, verified | retriever and indexer tests; MiniLM used in the Docker run and the evaluation |
| 4 | LangChain SQL generation | Done, verified | parser, repair loop, follow-up rewrite tests with a scripted LLM; real Gemini calls run in the UI and the evaluation |
| 5 | Validation and safe execution | Done, verified | large attack matrix in security tests; read-only, timeout, row limit, plan-cost tests against real PostgreSQL |
| 6 | Conversation and history | Done, verified | follow-up tests, history paging and persistence tests |
| 7 | FastAPI backend | Done, verified | API integration tests for every route, error shapes, live smoke test |
| 8 | Evaluation system | Done, verified | 53 questions + 28 adversarial; golden SQL self-check; full run with Gemini on 46 of 53 questions (7 acceptance examples pending), retrieval-only run, scripted-LLM tests |
| 9 | React dashboard | Done, verified | typecheck, production build, 24 vitest tests; response shapes checked against the live backend |
| 10 | Tests | Done | backend: 195 passed, 1 skipped; frontend: 24 passed |
| 11 | Docker | Done, verified | `docker-compose.yml`, backend and frontend Dockerfiles, nginx config; built and run on a MacBook, database seeded and queries executed |
| 12 | Documentation | Done | README, `docs/architecture.md`, `docs/setup.md`, `docs/api.md`, `docs/evaluation.md` |

## Acceptance checklist

### Database
- [x] at least 500 customers (520)
- [x] at least 100 products (120)
- [x] at least 10 categories (12)
- [x] at least 1000 orders (1650)
- [x] realistic relationships and constraints
- [x] reproducible seed (`SEED=20261114`)
- [x] read-only runtime role, no admin credentials in the API container

### Schema and RAG
- [x] schema discovered at runtime, nothing hardcoded
- [x] tables, columns, types, keys, relationships, comments captured
- [x] retrieval documents for tables, wide-table column groups, relationships
- [x] persistent vector index with staleness detection and manual rebuild
- [x] foreign key expansion with reasons
- [ ] real `all-MiniLM-L6-v2` run: code path written, not executed in the build environment

### SQL generation
- [x] structured output with Pydantic validation
- [x] bounded repair loop
- [x] clarification, cannot-answer and assumptions supported
- [x] follow-up questions with conversation context
- [ ] live Gemini generation: not executed in the build environment

### Safety
- [x] AST validation, single SELECT only, no DML/DDL, no system catalogs, no dangerous functions
- [x] column and table validation against the live schema
- [x] read-only transaction, statement timeout, row limit, plan-cost guard
- [x] backend revalidates before executing; generation never executes
- [x] secrets redacted from logs and error messages

### API and UI
- [x] all required endpoints plus `/api/chat`, `/api/schema/tables/{name}`, `/api/settings`
- [x] sidebar: New Query, Query History, Database Explorer, Schema Management, Evaluation, Settings
- [x] SQL viewer with copy, run, regenerate, results table with sort/paginate/CSV, automatic chart choice
- [x] retrieval debug panel, loading, empty and error states
- [x] no fake or hardcoded data in the frontend
- [ ] screenshots: not captured (no display in the build environment)

### Evaluation
- [x] at least 30 golden questions (53), categories covered
- [x] metrics computed by code from real runs; unmeasured values reported as n/a
- [x] adversarial SQL set: 28 of 28 rejected by the validator
- [x] full-pipeline run with Gemini: 46 of 53 questions evaluated, numbers in the README
- [ ] the last 7 acceptance examples (e02 to e08): blocked by the free-tier daily quota, finish with Resume

## Known limitations

- The full-pipeline evaluation is 46 of 53 questions (free-tier quota, 20 requests per day per model). The 7 missing ones are scored on validity and execution only, so accuracy is not affected.
- Docker Compose was built and run on one MacBook; other platforms are untested.
- Frontend component tests stub Recharts (jsdom has no layout); chart selection logic is tested separately.
- Single-user design: no authentication, rate limiting or multi-tenant isolation. Do not expose it to the internet as is.
- Only PostgreSQL and Gemini (plus an optional Ollama provider) are implemented.
