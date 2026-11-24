"""Shared test helpers: a hand-built mini schema and a scripted fake LLM."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from app.database.inspector import (
    ColumnInfo, ConstraintInfo, ForeignKeyInfo, IndexInfo, RelationshipInfo, SchemaInfo, TableInfo,
)


def _col(name, type_, *, pk=False, fk=False, nullable=False, comment=None, allowed=None, unique=False):
    return ColumnInfo(name=name, type=type_, nullable=nullable and not pk, primary_key=pk, foreign_key=fk,
                      comment=comment, allowed_values=allowed or [], unique=unique)


def make_schema() -> SchemaInfo:
    """customers <- orders <- order_items -> products -> categories (synthetic, for unit tests only)."""
    customers = TableInfo(
        schema_name="public", name="customers", comment="Registered customers.",
        columns=[_col("customer_id", "INTEGER", pk=True), _col("first_name", "VARCHAR(60)"), _col("last_name", "VARCHAR(60)"),
                 _col("email", "VARCHAR(160)", unique=True), _col("city", "VARCHAR(80)"), _col("state", "VARCHAR(80)"),
                 _col("registration_date", "DATE", comment="Date the customer registered.")],
        primary_key=["customer_id"],
        indexes=[IndexInfo(name="idx_customers_state", columns=["state"])],
    )
    orders = TableInfo(
        schema_name="public", name="orders", comment="Customer orders.",
        columns=[_col("order_id", "INTEGER", pk=True), _col("customer_id", "INTEGER", fk=True), _col("order_date", "DATE"),
                 _col("order_status", "VARCHAR(20)", allowed=["pending", "completed", "cancelled"]),
                 _col("total_amount", "NUMERIC(12, 2)")],
        primary_key=["order_id"],
        foreign_keys=[ForeignKeyInfo(columns=["customer_id"], referred_schema="public", referred_table="customers", referred_columns=["customer_id"])],
        constraints=[ConstraintInfo(kind="check", columns=["order_status"], definition="order_status IN ('pending','completed','cancelled')")],
    )
    items = TableInfo(
        schema_name="public", name="order_items", comment="Line items of an order.",
        columns=[_col("order_item_id", "INTEGER", pk=True), _col("order_id", "INTEGER", fk=True), _col("product_id", "INTEGER", fk=True),
                 _col("quantity", "INTEGER"), _col("unit_price", "NUMERIC(10, 2)")],
        primary_key=["order_item_id"],
        foreign_keys=[
            ForeignKeyInfo(columns=["order_id"], referred_schema="public", referred_table="orders", referred_columns=["order_id"]),
            ForeignKeyInfo(columns=["product_id"], referred_schema="public", referred_table="products", referred_columns=["product_id"]),
        ],
    )
    products = TableInfo(
        schema_name="public", name="products", comment="Product catalog.",
        columns=[_col("product_id", "INTEGER", pk=True), _col("product_name", "VARCHAR(160)"), _col("category_id", "INTEGER", fk=True),
                 _col("price", "NUMERIC(10, 2)"), _col("stock_quantity", "INTEGER")],
        primary_key=["product_id"],
        foreign_keys=[ForeignKeyInfo(columns=["category_id"], referred_schema="public", referred_table="categories", referred_columns=["category_id"])],
    )
    categories = TableInfo(
        schema_name="public", name="categories", comment="Product categories.",
        columns=[_col("category_id", "INTEGER", pk=True), _col("category_name", "VARCHAR(80)", unique=True), _col("description", "TEXT", nullable=True)],
        primary_key=["category_id"],
    )
    tables = [categories, customers, items, orders, products]
    rels = [
        RelationshipInfo(child_table="order_items", child_columns=["order_id"], parent_table="orders", parent_columns=["order_id"], cardinality="one-to-many"),
        RelationshipInfo(child_table="order_items", child_columns=["product_id"], parent_table="products", parent_columns=["product_id"], cardinality="one-to-many"),
        RelationshipInfo(child_table="orders", child_columns=["customer_id"], parent_table="customers", parent_columns=["customer_id"], cardinality="one-to-many"),
        RelationshipInfo(child_table="products", child_columns=["category_id"], parent_table="categories", parent_columns=["category_id"], cardinality="one-to-many"),
    ]
    return SchemaInfo(database="unit", schemas=["public"], available_schemas=["public"], tables=tables, relationships=rels,
                      inspected_at=datetime.now(timezone.utc), fingerprint="unit-test")


def gen_json(sql: str | None = "SELECT 1", *, status="ok", explanation="Explains the query.", tables=None,
             assumptions=None, confidence="high", clarification: str | None = None) -> str:
    return json.dumps({"status": status, "sql": sql, "explanation": explanation, "tables_used": tables or [],
                       "assumptions": assumptions or [], "confidence": confidence, "clarification_question": clarification})


class ScriptedLLM(Runnable):
    """A stand-in for the chat model. Responses come from a FIFO queue first, then from (substring -> reply) rules.

    This tests the pipeline around the model (prompting, parsing, retries, validation). It says nothing about
    real model accuracy.
    """

    def __init__(self):
        self.queue: list[Any] = []
        self.rules: list[tuple[str, Any]] = []
        self.calls: list[str] = []

    def invoke(self, input, config=None, **kwargs):
        text = input.to_string() if hasattr(input, "to_string") else str(input)
        self.calls.append(text)
        reply = None
        if self.queue:
            reply = self.queue.pop(0)
        else:
            for sub, r in self.rules:
                if sub.lower() in text.lower():
                    reply = r
                    break
        if reply is None:
            raise AssertionError("ScriptedLLM has no reply for this prompt:\n" + text[-400:])
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(text)
        return AIMessage(content=reply if isinstance(reply, str) else json.dumps(reply))
