"""Dynamic PostgreSQL schema discovery using SQLAlchemy's inspector.

Nothing in here knows about the demo database: it works for any compatible PostgreSQL schema.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

_QUOTED = re.compile(r"'((?:[^']|'')*)'")


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    comment: str | None = None
    primary_key: bool = False
    foreign_key: bool = False
    unique: bool = False
    allowed_values: list[str] = Field(default_factory=list)  # derived from CHECK ... IN (...) constraints


class ForeignKeyInfo(BaseModel):
    name: str | None = None
    columns: list[str]
    referred_schema: str | None = None
    referred_table: str
    referred_columns: list[str]


class IndexInfo(BaseModel):
    name: str
    columns: list[str]
    unique: bool = False


class ConstraintInfo(BaseModel):
    name: str | None = None
    kind: str  # primary_key | unique | check | foreign_key
    columns: list[str] = Field(default_factory=list)
    definition: str | None = None


class RelationshipInfo(BaseModel):
    """A directed relationship derived from a foreign key: child (FK holder) -> parent (referenced)."""

    child_table: str
    child_columns: list[str]
    parent_table: str
    parent_columns: list[str]
    cardinality: str  # "one-to-many" (parent has many children) or "one-to-one"

    def fk_sql(self) -> str:
        pairs = zip(self.child_columns, self.parent_columns)
        return " AND ".join(f"{self.child_table}.{c} = {self.parent_table}.{p}" for c, p in pairs)


class TableInfo(BaseModel):
    schema_name: str
    name: str
    comment: str | None = None
    columns: list[ColumnInfo]
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = Field(default_factory=list)
    indexes: list[IndexInfo] = Field(default_factory=list)
    constraints: list[ConstraintInfo] = Field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.name}"


class SchemaInfo(BaseModel):
    database: str
    schemas: list[str]  # schemas that were inspected
    available_schemas: list[str] = Field(default_factory=list)  # all schemas visible in the database
    tables: list[TableInfo]
    relationships: list[RelationshipInfo]
    inspected_at: datetime
    fingerprint: str

    def table(self, name: str) -> TableInfo | None:
        low = name.lower()
        for t in self.tables:
            if t.name.lower() == low or t.qualified_name.lower() == low:
                return t
        return None

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]


def _allowed_values(check_sql: str, column_names: list[str]) -> tuple[str | None, list[str]]:
    """Return (column, values) for CHECK constraints of the form col IN ('a','b') / col = ANY (ARRAY[...])."""
    mentioned = [c for c in column_names if re.search(rf"\b{re.escape(c)}\b", check_sql)]
    if len(mentioned) != 1:
        return None, []
    if not re.search(r"\bANY\b|\bIN\b|=", check_sql, re.IGNORECASE):
        return None, []
    values = [v.replace("''", "'") for v in _QUOTED.findall(check_sql)]
    return (mentioned[0], values) if values else (None, [])


class SchemaInspector:
    def __init__(self, engine: Engine, schemas: list[str]):
        self.engine = engine
        self.schemas = schemas

    def inspect(self) -> SchemaInfo:
        insp = inspect(self.engine)
        with self.engine.connect() as conn:
            database = conn.exec_driver_sql("SELECT current_database()").scalar_one()

        available = [s for s in insp.get_schema_names() if not s.startswith("pg_") and s != "information_schema"]
        tables: list[TableInfo] = []
        for schema in self.schemas:
            if schema not in available:
                continue
            for table_name in sorted(insp.get_table_names(schema=schema)):
                tables.append(self._inspect_table(insp, schema, table_name))

        relationships = self._relationships(tables)
        info = SchemaInfo(
            database=database,
            schemas=[s for s in self.schemas if s in available],
            available_schemas=available,
            tables=tables,
            relationships=relationships,
            inspected_at=datetime.now(timezone.utc),
            fingerprint="",
        )
        info.fingerprint = self._fingerprint(info)
        return info

    # ------------------------------------------------------------------
    def _inspect_table(self, insp, schema: str, name: str) -> TableInfo:
        pk = insp.get_pk_constraint(name, schema=schema) or {}
        pk_cols = list(pk.get("constrained_columns") or [])
        fks_raw = insp.get_foreign_keys(name, schema=schema)
        uniques = insp.get_unique_constraints(name, schema=schema)
        checks = insp.get_check_constraints(name, schema=schema)
        indexes_raw = insp.get_indexes(name, schema=schema)
        comment = (insp.get_table_comment(name, schema=schema) or {}).get("text")

        fk_cols = {c for fk in fks_raw for c in fk["constrained_columns"]}
        single_unique = {u["column_names"][0] for u in uniques if len(u["column_names"]) == 1}
        single_unique |= {i["column_names"][0] for i in indexes_raw if i.get("unique") and len(i["column_names"]) == 1}
        if len(pk_cols) == 1:
            single_unique.add(pk_cols[0])

        columns = [
            ColumnInfo(
                name=c["name"],
                type=str(c["type"]),
                nullable=bool(c.get("nullable", True)),
                default=str(c["default"]) if c.get("default") is not None else None,
                comment=c.get("comment"),
                primary_key=c["name"] in pk_cols,
                foreign_key=c["name"] in fk_cols,
                unique=c["name"] in single_unique,
            )
            for c in insp.get_columns(name, schema=schema)
        ]
        col_names = [c.name for c in columns]
        col_by_name = {c.name: c for c in columns}

        constraints: list[ConstraintInfo] = []
        if pk_cols:
            constraints.append(ConstraintInfo(name=pk.get("name"), kind="primary_key", columns=pk_cols))
        for u in uniques:
            constraints.append(ConstraintInfo(name=u.get("name"), kind="unique", columns=list(u["column_names"])))
        for fk in fks_raw:
            constraints.append(
                ConstraintInfo(
                    name=fk.get("name"),
                    kind="foreign_key",
                    columns=list(fk["constrained_columns"]),
                    definition=f"REFERENCES {fk['referred_table']} ({', '.join(fk['referred_columns'])})",
                )
            )
        for ck in checks:
            sqltext = ck.get("sqltext", "")
            col, values = _allowed_values(sqltext, col_names)
            if col and values:
                col_by_name[col].allowed_values = values
            constraints.append(
                ConstraintInfo(name=ck.get("name"), kind="check", columns=[col] if col else [], definition=sqltext)
            )

        return TableInfo(
            schema_name=schema,
            name=name,
            comment=comment,
            columns=columns,
            primary_key=pk_cols,
            foreign_keys=[
                ForeignKeyInfo(
                    name=fk.get("name"),
                    columns=list(fk["constrained_columns"]),
                    referred_schema=fk.get("referred_schema") or schema,
                    referred_table=fk["referred_table"],
                    referred_columns=list(fk["referred_columns"]),
                )
                for fk in fks_raw
            ],
            indexes=[
                IndexInfo(name=i["name"], columns=[c for c in i["column_names"] if c], unique=bool(i.get("unique")))
                for i in indexes_raw
            ],
            constraints=constraints,
        )

    @staticmethod
    def _relationships(tables: list[TableInfo]) -> list[RelationshipInfo]:
        known = {t.name for t in tables}
        rels: list[RelationshipInfo] = []
        for t in tables:
            unique_sets = [set(i.columns) for i in t.indexes if i.unique] + [set(t.primary_key)]
            for fk in t.foreign_keys:
                if fk.referred_table not in known:
                    continue
                one_to_one = any(set(fk.columns) == u for u in unique_sets if u)
                rels.append(
                    RelationshipInfo(
                        child_table=t.name,
                        child_columns=fk.columns,
                        parent_table=fk.referred_table,
                        parent_columns=fk.referred_columns,
                        cardinality="one-to-one" if one_to_one else "one-to-many",
                    )
                )
        return rels

    @staticmethod
    def _fingerprint(info: SchemaInfo) -> str:
        canonical = [
            {
                "t": t.qualified_name,
                "cmt": t.comment,
                "cols": [(c.name, c.type, c.nullable, c.comment) for c in t.columns],
                "pk": t.primary_key,
                "fks": [(fk.columns, fk.referred_table, fk.referred_columns) for fk in t.foreign_keys],
                "chk": sorted(c.definition or "" for c in t.constraints if c.kind == "check"),
            }
            for t in info.tables
        ]
        return hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str).encode()).hexdigest()[:16]
