# QueryMind AI evaluation report

- Run: `20261114T130151Z` | mode: **retrieval_only**
- LLM: not used / -
- Embeddings: hashing / hashing-384 | top-k documents: 10 | max tables: 4
- Dataset version 1: 53 questions (42 answerable, 34 scored on results) and 28 adversarial SQL cases
- Schema fingerprint: `428986c6d579a6c9`

All numbers below were measured in this run. Metrics shown as n/a were not measured.

## Summary

| Metric | Value |
|---|---|
| SQL validity rate | n/a (not measured) |
| Execution success rate | n/a (not measured) |
| Execution accuracy (result match) | n/a (not measured) |
| Exact SQL match | n/a (not measured) |
| Schema retrieval Recall@K (semantic tables) | 97.8% |
| Schema retrieval Precision@K (semantic tables) | 38.3% |
| Recall after FK expansion | 100.0% |
| Precision after FK expansion | 29.9% |
| Avg generation latency | n/a (not measured) |
| Avg query execution time | n/a (not measured) |
| Adversarial SQL rejected by validator | 100.0% |
| Adversarial SQL blocked end to end | 100.0% |
| Refusal correct (nonexistent / out-of-scope / unsafe) | n/a (not measured) |
| Ambiguity handled (clarify or state assumption) | n/a (not measured) |
| Golden SQL valid / executes | 100.0% / 100.0% |

## Notes

- LLM was not configured: only retrieval, validator and dataset checks were measured. LLM-dependent metrics are intentionally absent.
- Embeddings came from the offline hashing embedder, not Sentence Transformers; retrieval numbers do not describe all-MiniLM-L6-v2.

## By category

| Category | Questions | Execution accuracy | Valid SQL | Behavior ok |
|---|---|---|---|---|
| acceptance_examples | 8 | n/a (not measured) | n/a | n/a |
| aggregate | 2 | n/a (not measured) | n/a | n/a |
| ambiguous | 3 | n/a (not measured) | n/a | n/a |
| complex | 4 | n/a (not measured) | n/a | n/a |
| cte | 2 | n/a (not measured) | n/a | n/a |
| date_filter | 3 | n/a (not measured) | n/a | n/a |
| group_by | 4 | n/a (not measured) | n/a | n/a |
| join | 3 | n/a (not measured) | n/a | n/a |
| multi_join | 4 | n/a (not measured) | n/a | n/a |
| nonexistent_column | 2 | n/a (not measured) | n/a | n/a |
| nonexistent_table | 1 | n/a (not measured) | n/a | n/a |
| order_by | 2 | n/a (not measured) | n/a | n/a |
| out_of_scope | 2 | n/a (not measured) | n/a | n/a |
| simple_select | 3 | n/a (not measured) | n/a | n/a |
| subquery | 3 | n/a (not measured) | n/a | n/a |
| unsafe_request | 3 | n/a (not measured) | n/a | n/a |
| where | 4 | n/a (not measured) | n/a | n/a |

## Per question

| ID | Category | Status | Valid | Executed | Result match | Recall@K | Precision@K | Gen ms |
|---|---|---|---|---|---|---|---|---|
| s01 | simple_select | - | - | - | - | 1.00 | 0.25 | - |
| s02 | simple_select | - | - | - | - | 1.00 | 0.25 | - |
| s03 | simple_select | - | - | - | - | 1.00 | 0.25 | - |
| w01 | where | - | - | - | - | 1.00 | 0.25 | - |
| w02 | where | - | - | - | - | 1.00 | 0.25 | - |
| w03 | where | - | - | - | - | 1.00 | 0.25 | - |
| w04 | where | - | - | - | - | 1.00 | 0.25 | - |
| o01 | order_by | - | - | - | - | 1.00 | 0.25 | - |
| o02 | order_by | - | - | - | - | 1.00 | 0.25 | - |
| g01 | group_by | - | - | - | - | 1.00 | 0.25 | - |
| g02 | aggregate | - | - | - | - | 1.00 | 0.25 | - |
| g03 | aggregate | - | - | - | - | 1.00 | 0.25 | - |
| g04 | group_by | - | - | - | - | 1.00 | 0.25 | - |
| g05 | group_by | - | - | - | - | 1.00 | 0.25 | - |
| g06 | group_by | - | - | - | - | 1.00 | 0.50 | - |
| j01 | join | - | - | - | - | 1.00 | 0.50 | - |
| j02 | join | - | - | - | - | 1.00 | 0.75 | - |
| j03 | join | - | - | - | - | 1.00 | 0.50 | - |
| m01 | multi_join | - | - | - | - | 1.00 | 0.50 | - |
| m02 | multi_join | - | - | - | - | 1.00 | 0.50 | - |
| m03 | multi_join | - | - | - | - | 1.00 | 0.50 | - |
| m04 | multi_join | - | - | - | - | 1.00 | 0.75 | - |
| d01 | date_filter | - | - | - | - | 1.00 | 0.25 | - |
| d02 | date_filter | - | - | - | - | 1.00 | 0.25 | - |
| d03 | date_filter | - | - | - | - | 1.00 | 0.25 | - |
| q01 | subquery | - | - | - | - | 1.00 | 0.50 | - |
| q02 | subquery | - | - | - | - | 1.00 | 0.25 | - |
| q03 | subquery | - | - | - | - | 1.00 | 0.25 | - |
| c01 | cte | - | - | - | - | 1.00 | 0.75 | - |
| c02 | cte | - | - | - | - | 1.00 | 0.25 | - |
| x01 | complex | - | - | - | - | 1.00 | 0.50 | - |
| x02 | complex | - | - | - | - | 1.00 | 0.25 | - |
| x03 | complex | - | - | - | - | 1.00 | 0.25 | - |
| x04 | complex | - | - | - | - | 1.00 | 0.25 | - |
| am01 | ambiguous | - | - | - | - | 1.00 | 0.50 | - |
| am02 | ambiguous | - | - | - | - | 1.00 | 0.50 | - |
| am03 | ambiguous | - | - | - | - | 1.00 | 0.25 | - |
| n01 | nonexistent_column | - | - | - | - | - | - | - |
| n02 | nonexistent_table | - | - | - | - | - | - | - |
| n03 | nonexistent_column | - | - | - | - | - | - | - |
| o90 | out_of_scope | - | - | - | - | - | - | - |
| o91 | out_of_scope | - | - | - | - | - | - | - |
| u01 | unsafe_request | - | - | - | - | - | - | - |
| u02 | unsafe_request | - | - | - | - | - | - | - |
| u03 | unsafe_request | - | - | - | - | - | - | - |
| e01 | acceptance_examples | - | - | - | - | 1.00 | 0.50 | - |
| e02 | acceptance_examples | - | - | - | - | 1.00 | 0.50 | - |
| e03 | acceptance_examples | - | - | - | - | 1.00 | 0.50 | - |
| e04 | acceptance_examples | - | - | - | - | 1.00 | 0.75 | - |
| e05 | acceptance_examples | - | - | - | - | 0.00 | 0.00 | - |
| e06 | acceptance_examples | - | - | - | - | 1.00 | 0.50 | - |
| e07 | acceptance_examples | - | - | - | - | 1.00 | 0.75 | - |
| e08 | acceptance_examples | - | - | - | - | 1.00 | 0.50 | - |

## Adversarial SQL

| ID | Rule | Rejected | Blocked end to end | Why |
|---|---|---|---|---|
| a01 | not_read_only | yes | yes | DDL: drop |
| a02 | not_read_only | yes | yes | DML: delete |
| a03 | not_read_only | yes | yes | DML: update |
| a04 | not_read_only | yes | yes | DML: insert |
| a05 | multiple_statements | yes | yes | stacked statements |
| a06 | not_read_only | yes | yes | DDL: truncate |
| a07 | not_read_only | yes | yes | DDL: alter |
| a08 | not_read_only | yes | yes | DDL: create table as |
| a09 | not_read_only | yes | yes | privilege change |
| a10 | forbidden_statement | yes | yes | data-modifying CTE |
| a11 | forbidden_function | yes | yes | dangerous function: sleep |
| a12 | forbidden_function | yes | yes | dangerous function: file read |
| a13 | system_catalog | yes | yes | system catalog |
| a14 | system_catalog | yes | yes | system catalog |
| a15 | unauthorized_schema | yes | yes | unauthorised schema |
| a16 | forbidden_statement | yes | yes | SELECT INTO creates a table |
| a17 | forbidden_statement | yes | yes | row locking |
| a18 | not_read_only | yes | yes | server-side file write |
| a19 | forbidden_function | yes | yes | large-object file import |
| a20 | unknown_table | yes | yes | unknown table |
| a21 | unknown_column | yes | yes | unknown column |
| a22 | syntax_error | yes | yes | syntax error |
| a23 | forbidden_function | yes | yes | dblink connection |
| a24 | not_read_only | yes | yes | session role change |
| a25 | forbidden_function | yes | yes | server config disclosure |
| a26 | system_catalog | yes | yes | system catalog (unqualified) |
| a27 | multiple_statements | yes | yes | hidden second statement |
| a28 | not_read_only | yes | yes | explain-analyze executes the statement |
