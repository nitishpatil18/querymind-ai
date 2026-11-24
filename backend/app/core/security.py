"""Security policy for generated SQL: what is allowed, and helpers to mask sensitive values.

The policy is deliberately a deny-by-default design:
  * only a single SELECT / set-operation query is accepted (WITH is allowed when it only wraps SELECTs);
  * any AST node that can write, lock, define or administer is rejected;
  * functions unknown to the SQL parser must be on an explicit allow-list;
  * tables must be known, in an authorised schema, and never system catalogs.
"""
from __future__ import annotations

# --- statement shapes -------------------------------------------------------
# Function-name prefixes that are always rejected (clear error messages).
BLOCKED_FUNCTION_PREFIXES: tuple[str, ...] = (
    "pg_",  # pg_sleep, pg_read_file, pg_ls_dir, pg_terminate_backend, pg_advisory_lock, ...
    "lo_",  # large objects: lo_import / lo_export
    "dblink",
    "query_to_xml", "table_to_xml", "database_to_xml", "schema_to_xml", "cursor_to_xml",
    "set_config", "current_setting",
    "nextval", "setval", "currval", "lastval",
    "txid_", "inet_server", "inet_client",
    "lowrite", "loread",
)

# Functions the SQL parser does not model itself (parsed as "anonymous") that are safe to use.
SAFE_ANONYMOUS_FUNCTIONS: frozenset[str] = frozenset(
    {
        # math
        "abs", "ceil", "ceiling", "floor", "round", "trunc", "sign", "mod", "div", "power", "sqrt", "cbrt",
        "ln", "log", "log10", "exp", "greatest", "least", "width_bucket", "scale",
        # strings
        "lower", "upper", "initcap", "length", "char_length", "character_length", "octet_length", "left", "right",
        "lpad", "rpad", "ltrim", "rtrim", "btrim", "trim", "substr", "substring", "replace", "translate",
        "split_part", "strpos", "position", "concat", "concat_ws", "reverse", "repeat", "regexp_replace",
        "regexp_match", "regexp_matches", "to_char", "to_number", "format", "starts_with", "ascii", "chr",
        # dates / times
        "age", "date_part", "date_trunc", "date_bin", "extract", "make_date", "make_interval", "make_timestamp",
        "to_date", "to_timestamp", "justify_days", "justify_hours", "justify_interval", "isfinite", "timezone",
        "now", "clock_timestamp", "current_date", "current_time", "current_timestamp", "localtime", "localtimestamp",
        # null handling / conditional
        "coalesce", "nullif",
        # aggregates / statistics
        "count", "sum", "avg", "min", "max", "bool_and", "bool_or", "every", "string_agg", "array_agg",
        "stddev", "stddev_pop", "stddev_samp", "variance", "var_pop", "var_samp", "corr", "covar_pop", "covar_samp",
        "regr_slope", "regr_intercept", "regr_r2", "mode", "percentile_cont", "percentile_disc",
        # window functions
        "row_number", "rank", "dense_rank", "percent_rank", "cume_dist", "ntile", "lag", "lead",
        "first_value", "last_value", "nth_value",
        # arrays / sets
        "unnest", "array_length", "cardinality", "array_to_string", "generate_series", "array_position",
        # misc
        "md5", "random",
    }
)

SYSTEM_SCHEMAS: frozenset[str] = frozenset({"pg_catalog", "information_schema", "pg_toast", "pg_temp"})

MAX_JOINS = 10  # guard against runaway cartesian-style queries
MAX_SUBQUERY_DEPTH = 6
