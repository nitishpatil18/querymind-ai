"""AST-based SQL validation: the single gate every generated or user-supplied statement passes through."""
from __future__ import annotations

import logging

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp
from sqlglot.errors import ErrorLevel, OptimizeError, ParseError, SqlglotError, TokenError
from sqlglot.optimizer.qualify import qualify
from sqlglot.schema import MappingSchema

from app.config import Settings, get_settings
from app.core import security
from app.database.inspector import SchemaInfo
from app.utils import sql_utils

logger = logging.getLogger(__name__)
logging.getLogger("sqlglot").setLevel(logging.ERROR)  # silence 'unsupported syntax' notices; we reject those anyway


class ValidationIssue(BaseModel):
    code: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    normalized_sql: str | None = None
    statement_type: str | None = None
    dialect: str = "postgres"
    tables: list[str] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def error_summary(self) -> str:
        return "; ".join(e.message for e in self.errors)


class ValidationService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------
    def validate(self, sql: str, schema: SchemaInfo | None = None) -> ValidationResult:
        result = ValidationResult(valid=False)

        def fail(code: str, message: str) -> ValidationResult:
            result.errors.append(ValidationIssue(code=code, message=message))
            return result

        if not sql or not sql.strip():
            return fail("empty", "The SQL statement is empty.")
        if len(sql) > self.settings.max_sql_length:
            return fail("too_long", f"The SQL statement is too long (limit {self.settings.max_sql_length} characters).")

        try:
            statements = [s for s in sqlglot.parse(sql, dialect="postgres", error_level=ErrorLevel.RAISE) if s is not None]
        except (ParseError, TokenError) as exc:
            first = str(exc).splitlines()[0] if str(exc) else "invalid syntax"
            return fail("syntax_error", f"SQL syntax error: {first[:200]}")
        except SqlglotError:
            return fail("syntax_error", "The SQL statement could not be parsed.")

        if not statements:
            return fail("empty", "The SQL statement is empty.")
        if len(statements) > 1:
            return fail("multiple_statements", "Only a single SQL statement is allowed.")

        root = statements[0]
        result.statement_type = type(root).__name__.upper()

        # 1. statement shape ------------------------------------------------
        if not sql_utils.is_query_root(root):
            return fail("not_read_only", f"Only read-only SELECT queries are allowed (got {result.statement_type}).")
        if isinstance(root, exp.Subquery):
            root = root.unnest() if hasattr(root, "unnest") else root

        # 2. forbidden nodes anywhere in the tree (INSERT in CTE, SELECT INTO, FOR UPDATE, ...)
        forbidden = {label for n in root.walk() if (label := sql_utils.forbidden_label(n))}
        for label in sorted(forbidden):
            if label == "INTO":
                fail("forbidden_statement", "SELECT ... INTO creates a table and is not allowed.")
            elif label == "LOCK":
                fail("forbidden_statement", "Row-locking clauses (FOR UPDATE / FOR SHARE) are not allowed.")
            else:
                fail("forbidden_statement", f"{label} is not allowed: only read-only queries can run.")
        if result.errors:
            return result

        # 3. functions ----------------------------------------------------------
        for name, anonymous in sql_utils.function_names(root):
            if name.startswith(security.BLOCKED_FUNCTION_PREFIXES):
                fail("forbidden_function", f"The function {name}() is not allowed.")
            elif anonymous and name not in security.SAFE_ANONYMOUS_FUNCTIONS:
                fail("forbidden_function", f"The function {name}() is not on the list of permitted functions.")
        if result.errors:
            return result

        # 4. tables -------------------------------------------------------------
        allowed_schemas = {s.lower() for s in self.settings.allowed_schemas}
        known_tables = {t.name.lower(): t for t in schema.tables} if schema else None
        tables_used: list[str] = []
        for t in sql_utils.referenced_tables(root):
            name, db, catalog = t.name.lower(), (t.args.get("db").name.lower() if t.args.get("db") else None), t.args.get("catalog")
            if catalog:
                fail("unauthorized_schema", "Cross-database references are not allowed.")
                continue
            if (db and db in security.SYSTEM_SCHEMAS) or name.startswith("pg_") or (db is None and name in ("information_schema",)):
                fail("system_catalog", f"Access to system catalogs is not allowed ({db + '.' if db else ''}{name}).")
                continue
            if db and db not in allowed_schemas:
                fail("unauthorized_schema", f"Schema '{db}' is not authorised for queries.")
                continue
            if known_tables is not None and name not in known_tables:
                fail("unknown_table", f"Table '{name}' does not exist in the authorised schema.")
                continue
            if name not in tables_used:
                tables_used.append(name)
        result.tables = tables_used
        if result.errors:
            return result

        # 5. complexity guards ------------------------------------------------
        if sql_utils.count_joins(root) > security.MAX_JOINS:
            return fail("too_complex", f"Too many JOINs (limit {security.MAX_JOINS}).")
        if sql_utils.max_select_depth(root) > security.MAX_SUBQUERY_DEPTH:
            return fail("too_complex", f"Subqueries are nested too deeply (limit {security.MAX_SUBQUERY_DEPTH}).")

        # 6. column references against the discovered schema ---------------------
        if schema is not None:
            problem = self._check_columns(root, schema, result)
            if problem:
                return fail("unknown_column", problem)

        result.normalized_sql = sql_utils.to_sql(root)
        result.valid = True
        return result

    # ------------------------------------------------------------------
    def _check_columns(self, root: exp.Expression, schema: SchemaInfo, result: ValidationResult) -> str | None:
        mapping: dict[str, dict[str, dict[str, str]]] = {}
        for t in schema.tables:
            mapping.setdefault(t.schema_name, {})[t.name] = {c.name: c.type for c in t.columns}
        default_schema = next((s for s in self.settings.allowed_schemas if s in mapping), None)
        try:
            qualify(
                root.copy(),
                schema=MappingSchema(mapping, dialect="postgres"),
                db=default_schema,
                dialect="postgres",
                validate_qualify_columns=True,
                expand_stars=True,
            )
        except OptimizeError as exc:
            msg = str(exc).splitlines()[0] if str(exc) else "unknown column"
            hint = " (if the column exists, it may be ambiguous: qualify it with its table alias)" if "could not be resolved" in msg else ""
            return f"Invalid column reference: {msg[:200]}{hint}"
        except Exception as exc:  # parser/optimizer limitation, not a policy problem
            logger.warning("column check skipped: %s", exc.__class__.__name__)
            result.warnings.append("Column references could not be fully verified against the schema.")
        return None
