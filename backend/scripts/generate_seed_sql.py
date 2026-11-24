"""Regenerate database/init/02_seed.sql from the deterministic generator.

Usage (from backend/):  python -m scripts.generate_seed_sql
"""
from pathlib import Path

from app.database.initialization import REPO_ROOT, render_seed_sql
from app.database.seed_data import generate

if __name__ == "__main__":
    data = generate()
    target = REPO_ROOT / "database" / "init" / "02_seed.sql"
    target.write_text(render_seed_sql(data))
    print(
        f"wrote {target} | customers={len(data.customers)} categories={len(data.categories)} "
        f"products={len(data.products)} orders={len(data.orders)} order_items={len(data.order_items)} "
        f"payments={len(data.payments)}"
    )
