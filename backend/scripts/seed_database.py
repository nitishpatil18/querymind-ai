"""Reload deterministic seed data into an existing demo schema (TRUNCATE + INSERT).

Usage (from backend/):  python -m scripts.seed_database
"""
import sys

from app.config import get_settings
from app.database.initialization import render_seed_sql, run_script


def main() -> int:
    settings = get_settings()
    if settings.database_admin_url is None:
        print("DATABASE_ADMIN_URL is not set.", file=sys.stderr)
        return 2
    url = settings.database_admin_url.get_secret_value()
    run_script(url, "TRUNCATE payments, order_items, orders, products, categories, customers RESTART IDENTITY CASCADE;")
    run_script(url, render_seed_sql())
    print("seed data loaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
