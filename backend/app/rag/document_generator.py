"""Turn discovered schema metadata into structured, embeddable documents.

Only schema metadata and documentation are indexed. Row data is never read here.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.database.inspector import ColumnInfo, RelationshipInfo, SchemaInfo, TableInfo


class SchemaDocument(BaseModel):
    doc_id: str
    text: str
    metadata: dict[str, str | int | bool] = Field(default_factory=dict)


def _singular(word: str) -> str:
    w = word.lower().replace("_", " ")
    if w.endswith("ies") and len(w) > 3:
        return w[:-3] + "y"
    if w.endswith("ses") or w.endswith("xes"):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def describe_column(col: ColumnInfo, *, with_comment: bool = True) -> str:
    flags = []
    if col.primary_key:
        flags.append("PRIMARY KEY")
    if col.foreign_key:
        flags.append("FOREIGN KEY")
    if col.unique and not col.primary_key:
        flags.append("UNIQUE")
    if not col.nullable and not col.primary_key:
        flags.append("NOT NULL")
    line = f"- {col.name}: {col.type}"
    if flags:
        line += ", " + ", ".join(flags)
    if col.allowed_values:
        line += "; allowed values: " + ", ".join(f"'{v}'" for v in col.allowed_values)
    if with_comment and col.comment:
        line += f"  -- {col.comment}"
    return line


def relationship_sentences(table: TableInfo, schema: SchemaInfo) -> list[str]:
    lines: list[str] = []
    for rel in schema.relationships:
        if rel.child_table == table.name:  # this table holds the FK
            lines.append(
                f"- Each {_singular(rel.child_table)} belongs to one {_singular(rel.parent_table)}. "
                f"Foreign key: {rel.child_table}.{', '.join(rel.child_columns)} references "
                f"{rel.parent_table}.{', '.join(rel.parent_columns)}."
            )
        elif rel.parent_table == table.name:  # other tables reference this one
            many = "multiple" if rel.cardinality == "one-to-many" else "one"
            lines.append(
                f"- One {_singular(rel.parent_table)} can have {many} {rel.child_table} record(s). "
                f"Foreign key: {rel.child_table}.{', '.join(rel.child_columns)} references "
                f"{rel.parent_table}.{', '.join(rel.parent_columns)}."
            )
    return lines


def render_table_document(table: TableInfo, schema: SchemaInfo, *, include_relationships: bool = True) -> str:
    """Full, human-readable description of a table (also used as LLM context)."""
    lines = [f"Table: {table.name}"]
    if table.schema_name != "public":
        lines[0] += f" (schema: {table.schema_name})"
    lines.append(f"Description: {table.comment or 'No description available.'}")
    lines.append("Columns:")
    lines.extend(describe_column(c) for c in table.columns)
    if include_relationships:
        rels = relationship_sentences(table, schema)
        if rels:
            lines.append("Relationships:")
            lines.extend(rels)
    index_lines = [f"- {i.name} ({', '.join(i.columns)}){' UNIQUE' if i.unique else ''}" for i in table.indexes]
    if index_lines:
        lines.append("Indexes:")
        lines.extend(index_lines)
    checks = [c for c in table.constraints if c.kind == "check" and c.definition]
    if checks:
        lines.append("Check constraints:")
        lines.extend(f"- {c.definition}" for c in checks)
    return "\n".join(lines)


def render_relationship(rel: RelationshipInfo) -> str:
    return (
        f"Relationship: {rel.child_table} -> {rel.parent_table} ({rel.cardinality}). "
        f"Each {_singular(rel.child_table)} row references one {_singular(rel.parent_table)} row. "
        f"Join condition: {rel.fk_sql()}."
    )


def generate_documents(schema: SchemaInfo, column_chunk_size: int = 12) -> list[SchemaDocument]:
    docs: list[SchemaDocument] = []
    for table in schema.tables:
        related = sorted(
            {r.parent_table for r in schema.relationships if r.child_table == table.name}
            | {r.child_table for r in schema.relationships if r.parent_table == table.name}
        )
        base_meta = {
            "schema": table.schema_name,
            "table": table.name,
            "related_tables": ",".join(related),
            "tables": table.name,
        }
        if len(table.columns) <= column_chunk_size:
            docs.append(
                SchemaDocument(
                    doc_id=f"{table.qualified_name}::table",
                    text=render_table_document(table, schema),
                    metadata={**base_meta, "doc_type": "table", "chunk": 0},
                )
            )
            continue

        # Wide table: an overview document plus column chunks that repeat the table header.
        overview = [f"Table: {table.name}", f"Description: {table.comment or 'No description available.'}"]
        overview.append("Column names: " + ", ".join(c.name for c in table.columns))
        if table.primary_key:
            overview.append("Primary key: " + ", ".join(table.primary_key))
        overview.extend(relationship_sentences(table, schema))
        docs.append(
            SchemaDocument(
                doc_id=f"{table.qualified_name}::table",
                text="\n".join(overview),
                metadata={**base_meta, "doc_type": "table", "chunk": 0},
            )
        )
        for i in range(0, len(table.columns), column_chunk_size):
            chunk = table.columns[i : i + column_chunk_size]
            text = "\n".join(
                [f"Table: {table.name}", f"Description: {table.comment or ''}", "Columns:"]
                + [describe_column(c) for c in chunk]
            )
            docs.append(
                SchemaDocument(
                    doc_id=f"{table.qualified_name}::columns::{i // column_chunk_size + 1}",
                    text=text,
                    metadata={**base_meta, "doc_type": "columns", "chunk": i // column_chunk_size + 1},
                )
            )

    for rel in schema.relationships:
        child = schema.table(rel.child_table)
        docs.append(
            SchemaDocument(
                doc_id=f"rel::{rel.child_table}.{'+'.join(rel.child_columns)}->{rel.parent_table}",
                text=render_relationship(rel),
                metadata={
                    "schema": child.schema_name if child else "",
                    "table": rel.child_table,
                    "related_tables": rel.parent_table,
                    "tables": f"{rel.child_table},{rel.parent_table}",
                    "doc_type": "relationship",
                    "chunk": 0,
                },
            )
        )
    return docs
