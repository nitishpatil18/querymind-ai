# Setup

Two ways to run the project. Docker is the simplest. The local setup is for development.

## Option A: Docker Compose

Requires Docker with Compose v2 and a Gemini API key (https://aistudio.google.com/apikey).

```bash
cp .env.example .env
# edit .env: set GOOGLE_API_KEY, and change the two database passwords
docker compose up --build
```

- App: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

What happens on first start:

1. Postgres runs `database/init/01_schema.sql`, `02_seed.sql` and `03_roles.sql` (tables, demo data, read-only role).
2. The backend starts with the read-only URL only, loads MiniLM (baked into the image), inspects the schema and builds the vector index in the background.
3. The sidebar health dot turns green when the index is ready. Until then Settings and Schema Management show the state.

Reset everything, including the database and index:

```bash
docker compose down -v
```

Notes:

- The seed script only runs when the `pgdata` volume is empty. After editing seed or schema SQL, run `docker compose down -v` first.
- Ports are bound to `127.0.0.1`. Change them with `POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`.
- Without `GOOGLE_API_KEY` everything except SQL generation works (explorer, schema, validation, execution, retrieval-only evaluation).

## Option B: local development

Requires Python 3.10 or newer (the Docker image uses 3.12; the test suite was run on 3.10), Node 22, PostgreSQL 16.

### 1. Database

```bash
createdb querymind    # or use any existing empty database
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # set DATABASE_URL, DATABASE_ADMIN_URL, GOOGLE_API_KEY
python -m scripts.initialize_database      # schema + seed + read-only role
```

`initialize_database` uses `DATABASE_ADMIN_URL`. Add `--force` to drop and recreate the demo tables, `--no-seed` to create the schema only. The seed is deterministic: 520 customers, 12 categories, 120 products, 1650 orders, 3386 order items, 1727 payments.

### 2. Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The first start downloads `all-MiniLM-L6-v2` (about 90 MB) and builds the index. To rebuild it manually: `python -m scripts.rebuild_index`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api and /health to localhost:8000
```

Set `VITE_BACKEND_URL` if the backend is elsewhere.

## Tests

Backend (from `backend/`):

```bash
pip install -r requirements-dev.txt
pytest
```

The suite needs a disposable PostgreSQL. It uses `TEST_DATABASE_ADMIN_URL` if set (it creates and drops a `querymind_test` database there), otherwise it starts an embedded server from `pixeltable-pgserver`. It never touches your demo database. Tests use a scripted fake LLM and an offline hashing embedder, so they need no network or API key. One test that loads the real MiniLM model is marked `slow` and skipped when the model is unavailable.

Frontend (from `frontend/`):

```bash
npm test             # vitest + testing-library
npm run typecheck
npm run build
```

## Using your own database

The system reads whatever schema `DATABASE_URL` points at. Set `APP_SCHEMAS` to the schemas to index (default `public`), create a read-only role for it, restart, and rebuild the index from Schema Management. The golden dataset is specific to the demo e-commerce data, so evaluation results only mean something on that database.

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | none | read-only connection used by the API |
| `DATABASE_ADMIN_URL` | none | only for init and seed scripts |
| `APP_SCHEMAS` | `public` | schemas to inspect and allow |
| `LLM_PROVIDER` / `LLM_MODEL` | `gemini` / `gemini-3.8-flash` | model selection |
| `LLM_THINKING_LEVEL` | empty | Gemini 3+ thinking effort: `minimal`, `low`, `medium`, `high`. Lower is faster; empty uses the model default |
| `GOOGLE_API_KEY` | empty | required for SQL generation |
| `LLM_TEMPERATURE` | `0` | |
| `LLM_TIMEOUT_SECONDS` | `60` | |
| `GENERATION_MAX_ATTEMPTS` | `3` | generation plus repair attempts |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | |
| `RETRIEVAL_TOP_K` | `10` | schema documents retrieved |
| `RETRIEVAL_MAX_TABLES` | `4` | tables kept from semantic ranking |
| `RETRIEVAL_EXPAND_MAX` | `3` | extra tables added via foreign keys |
| `MAX_RESULT_ROWS` | `1000` | hard cap on returned rows |
| `STATEMENT_TIMEOUT_MS` | `15000` | per-query timeout |
| `MAX_PLAN_COST` | `10000000` | refuse plans costlier than this |
| `CONVERSATION_CONTEXT_TURNS` | `4` | turns passed to follow-up rewriting |
| `CORS_ORIGINS` | `http://localhost:5173` | |
| `DATA_DIR` | `./data` | Chroma index, history, reports |

## Troubleshooting

- Health shows `llm: degraded`: `GOOGLE_API_KEY` is empty.
- `index_not_ready` (409): the first index build is still running. Check Schema Management.
- Generated SQL is rejected as touching an unknown table: the index is stale. Rebuild it from Schema Management.
- Docker build is slow the first time: it installs CPU PyTorch and downloads MiniLM into the image.
