# Evaluation

The evaluation measures the real pipeline against `backend/evaluation/golden_questions.json`. Nothing in the UI or in the reports is precomputed or hand-entered. A metric that was not measured is shown as `n/a`.

## Dataset

- 53 questions, 28 adversarial SQL statements (dataset version 1)
- Categories: simple_select, where, order_by, aggregate, group_by, join, multi_join, subquery, cte, date_filter, complex, ambiguous, nonexistent_table, nonexistent_column, out_of_scope, unsafe_request, acceptance_examples
- Each question has `expected_behavior`:
  - `answer`: must produce valid SQL
  - `refuse`: must not produce SQL (missing table or column, out of scope, write request)
  - `clarify_or_assume`: must ask for clarification or state an assumption
- Each answerable question has a reference SQL and a `scoring` mode:
  - `result`: the generated SQL must return the same result as the reference
  - `executes`: the definition is open, so only validity and successful execution count
- Reference SQL is deterministic. The dataset test runs every reference query and checks it validates, executes and is non-empty.

## Metrics

| Metric | How it is computed |
|---|---|
| Execution accuracy | result-set match against the reference, over `result`-scored questions. Row count and column count must match; values are normalized before comparing; row order is ignored unless the question is marked ordered; column names and column order are ignored |
| Execution accuracy, extra columns allowed | like execution accuracy, but the answer may contain additional columns as long as some subset of its columns matches the reference. A query that returns one useful extra column is not wrong, so this is reported next to the strict number, never instead of it |
| Questions evaluated | questions where the model gave an answer. Questions that failed because of the provider (rate limit, quota, overload) are listed as errors and left out of every rate, so an unavailable API never lowers the score |
| SQL validity | generated SQL passes the validator, over answerable questions |
| Execution success | generated SQL runs without error |
| Exact SQL match | normalized SQL string equality; informational only, since equivalent queries differ textually |
| Recall@K and Precision@K | expected tables vs tables from the top-K semantic hits, before expansion |
| Recall and Precision after expansion | same, after foreign key expansion (what the model actually sees) |
| Adversarial rejection | share of the 28 unsafe statements rejected by the validator, and share blocked end to end |
| Refusal correct, ambiguity handled | behavior checks for `refuse` and `clarify_or_assume` questions |
| Latency | mean generation time and mean execution time |

## Modes

- `full`: needs `GOOGLE_API_KEY`. Runs everything above.
- `retrieval_only`: used automatically when no key is configured. Measures retrieval, the validator on adversarial statements, and the golden SQL self-check. LLM metrics are absent, not zero.

## Provider limits, retries and resuming

Free Gemini keys allow very few requests (20 per day per model at the time of writing, 5 per minute). The evaluation is built to survive that and to stay honest about it:

- rate limits are retried with waiting (10, 20, 40, 60 seconds); overloaded or intermittently missing models get one retry after 30 seconds, because on a free key failed requests use quota too. Two such questions in a row stop the run
- when the provider reports the daily quota as used up, the run stops calling the model at once. The remaining questions are marked as errors (not as wrong answers), retrieval is still measured for them, and a note in the report says why
- failed questions never count against accuracy; the report shows how many were evaluated out of the total
- **Resume** keeps every answer from the previous report that did not fail and runs only the unfinished questions. It applies only when the mode, dataset version and database schema are unchanged. Each answer stores the model that produced it and the report notes list the models involved, so a resumed run stays traceable. For clean numbers, finish a run with one model

On a free key a full run therefore takes a few days: run, wait for the daily reset, press Resume. A paid key removes the wait.

## Running

UI: Evaluation page, Run evaluation.

CLI (from `backend/`):

```bash
python -m scripts.run_evaluation                 # full when a key is set, otherwise retrieval_only
python -m scripts.run_evaluation --mode retrieval_only
```

UI: when the latest full report has unfinished questions, a Resume button appears.

API: `POST /api/evaluation/run` with an optional body `{"mode": "full", "resume": true}`, then poll `GET /api/evaluation/results`.

Each run writes `latest.json`, `latest.md` and `report_<run id>.json` to `EVALUATION_REPORTS_DIR`.

## Results included in this repository

`backend/evaluation/reports/offline_retrieval_only_report.md` is a real run, with these limits stated up front:

- mode `retrieval_only`: no language model was available, so SQL validity, execution accuracy and latency were not measured
- embeddings were the offline hashing embedder, not `all-MiniLM-L6-v2`, so the retrieval numbers do not describe the MiniLM setup

Measured in that run: semantic Recall@K 97.8%, Precision@K 38.3%, recall after expansion 100.0%, precision after expansion 29.9%, adversarial statements rejected by the validator 28 of 28, golden SQL valid and executing 100%.

Precision is low by design: the top-K and expansion step favour recall, because a missing table makes the question unanswerable while an extra table only adds prompt tokens.

The full-pipeline numbers with Gemini (46 of 53 questions at the time of writing) are in the README. Expect them to differ between models and between runs.
