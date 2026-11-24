"""Create the schema, load seed data and create the read-only role (idempotent).

Usage (from backend/):
    python -m scripts.initialize_database            # create what is missing
    python -m scripts.initialize_database --force    # drop and recreate the demo tables

Needs DATABASE_ADMIN_URL (owner/superuser). The read-only role name and password are taken from DATABASE_URL.
"""
import argparse
import sys

from sqlalchemy.engine import make_url

from app.config import get_settings
from app.database.initialization import initialize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="drop and recreate demo tables")
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if settings.database_admin_url is None:
        print("DATABASE_ADMIN_URL is not set.", file=sys.stderr)
        return 2
    ro = make_url(settings.database_url.get_secret_value())
    result = initialize(
        settings.database_admin_url.get_secret_value(), ro.username, ro.password or "", seed=not args.no_seed, force=args.force
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
