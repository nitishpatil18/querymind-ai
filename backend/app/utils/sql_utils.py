"""Pure helpers for working with sqlglot expression trees."""
from __future__ import annotations

from sqlglot import exp

# Node classes that mean "this statement can write, lock, define, administer or change session state".
_FORBIDDEN_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Drop", "Alter", "AlterTable", "AlterColumn", "AlterRename", "Create",
    "TruncateTable", "Command", "Copy", "Grant", "Revoke", "Set", "SetItem", "Use", "Transaction", "Commit",
    "Rollback", "Into", "Lock", "Pragma", "Declare", "Attach", "Detach", "Analyze", "Refresh", "Comment",
    "Describe", "Show", "Cache", "Uncache", "LoadData", "Execute", "Kill", "Vacuum", "Fetch", "Export",
)
FORBIDDEN_NODE_TYPES: tuple[type, ...] = tuple(
    t for t in (getattr(exp, n, None) for n in _FORBIDDEN_NAMES) if isinstance(t, type)
)
_BASE_FORBIDDEN = tuple(t for t in (getattr(exp, "DDL", None), getattr(exp, "DML", None)) if isinstance(t, type))

_SET_OP = getattr(exp, "SetOperation", exp.Union)


def forbidden_label(node: exp.Expression) -> str | None:
    """Return a statement label (e.g. 'DELETE') if the node is not allowed in read-only SQL."""
    if isinstance(node, FORBIDDEN_NODE_TYPES) or (_BASE_FORBIDDEN and isinstance(node, _BASE_FORBIDDEN)):
        return type(node).__name__.upper()
    return None


def is_query_root(node: exp.Expression) -> bool:
    """SELECT, set operations (UNION/INTERSECT/EXCEPT) or a parenthesised query."""
    if isinstance(node, exp.Subquery):
        inner = node.this
        return inner is not None and is_query_root(inner)
    return isinstance(node, (exp.Select, _SET_OP))


def cte_names(root: exp.Expression) -> set[str]:
    return {c.alias_or_name.lower() for c in root.find_all(exp.CTE) if c.alias_or_name}


def referenced_tables(root: exp.Expression) -> list[exp.Table]:
    """Real table references (CTE references and table functions are excluded)."""
    ctes = cte_names(root)
    tables: list[exp.Table] = []
    for t in root.find_all(exp.Table):
        if not isinstance(t.this, exp.Identifier):
            continue  # table-valued function: checked through the function rules
        if not t.args.get("db") and not t.args.get("catalog") and t.name.lower() in ctes:
            continue
        tables.append(t)
    return tables


def function_names(root: exp.Expression) -> list[tuple[str, bool]]:
    """(lower-case name, is_anonymous) for every function call in the tree."""
    out: list[tuple[str, bool]] = []
    for f in root.find_all(exp.Func):
        if isinstance(f, exp.Anonymous):
            out.append((str(f.name).lower(), True))
        else:
            out.append((f.sql_name().lower(), False))
    return out


def count_joins(root: exp.Expression) -> int:
    return sum(1 for _ in root.find_all(exp.Join))


def max_select_depth(root: exp.Expression) -> int:
    depth = 0
    for s in root.find_all(exp.Select):
        d, p = 1, s.parent
        while p is not None:
            if isinstance(p, exp.Select):
                d += 1
            p = p.parent
        depth = max(depth, d)
    return depth


def to_sql(root: exp.Expression, *, pretty: bool = True) -> str:
    return root.sql(dialect="postgres", pretty=pretty)
