from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker



def _load_database_url(cli_url: str | None) -> str:
    if cli_url:
        return cli_url
    env_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
    if env_url:
        return env_url
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    ini_url = config.get_main_option("sqlalchemy.url")
    if not ini_url:
        raise RuntimeError("No DATABASE_URL or sqlalchemy.url configured.")
    return ini_url


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _reset_postgres_db(database_url: str, db_name_override: str | None) -> str:
    url = make_url(database_url)
    target_db = db_name_override or url.database
    if not target_db:
        raise RuntimeError("Postgres URL is missing a database name.")

    maintenance_db = url.set(database="postgres")
    engine = create_engine(maintenance_db, future=True, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :db_name AND pid <> pg_backend_pid();
                    """
                ),
                {"db_name": target_db},
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS \"{target_db}\""))
            conn.execute(text(f"CREATE DATABASE \"{target_db}\""))
    finally:
        engine.dispose()

    return url.set(database=target_db).render_as_string(hide_password=False)


def _reset_sqlite_db(database_url: str) -> str:
    url = make_url(database_url)
    if url.database and url.database != ":memory:":
        db_path = Path(url.database)
        if db_path.exists():
            db_path.unlink()
    return database_url


def _seed_minimal_business(database_url: str) -> None:
    os.environ.setdefault("DATABASE_URL", database_url)
    from backend.app.models import Business, Organization

    engine = create_engine(database_url, future=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        org = Organization(name="Demo Org")
        session.add(org)
        session.flush()
        business = Business(org_id=org.id, name="Demo Business")
        session.add(business)
        session.commit()
    finally:
        session.close()
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the development database.")
    parser.add_argument("--url", help="Override the database URL.")
    parser.add_argument("--db-name", help="Override the database name (Postgres only).")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset.")
    parser.add_argument("--seed", action="store_true", help="Seed a minimal business record.")
    args = parser.parse_args()

    if not args.yes:
        print("Refusing to reset database without --yes.")
        return 1

    database_url = _load_database_url(args.url)
    url = make_url(database_url)

    if url.get_backend_name().startswith("postgres"):
        database_url = _reset_postgres_db(database_url, args.db_name)
    elif url.get_backend_name().startswith("sqlite"):
        database_url = _reset_sqlite_db(database_url)
    else:
        print(f"Unsupported database backend: {url.get_backend_name()}")
        return 1

    config = _alembic_config(database_url)
    command.upgrade(config, "head")

    if args.seed:
        _seed_minimal_business(database_url)

    print("DONE")
    print(f"Database URL: {make_url(database_url).render_as_string(hide_password=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
