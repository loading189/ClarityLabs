from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _load_database_url() -> str:
    env_url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
    if env_url:
        return env_url

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    ini_url = config.get_main_option("sqlalchemy.url")
    if not ini_url:
        raise RuntimeError("No DATABASE_URL or sqlalchemy.url configured.")
    return ini_url


def _load_alembic_script() -> ScriptDirectory:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    return ScriptDirectory.from_config(config)


def _fetch_db_revision(database_url: str) -> str | None:
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.first()
            return row[0] if row else None
    except Exception as exc:  # pragma: no cover - best effort diagnostics
        message = str(exc).lower()
        if "alembic_version" in message or "no such table" in message:
            return None
        raise
    finally:
        engine.dispose()


def main() -> int:
    errors = []
    database_url = _load_database_url()
    url = make_url(database_url)

    script = _load_alembic_script()
    heads = script.get_heads()

    db_revision = _fetch_db_revision(database_url)

    print("DB sanity report")
    print(f"- SQLAlchemy URL: {url.render_as_string(hide_password=True)}")
    print(f"- Alembic heads in repo: {heads}")
    print(f"- DB alembic_version: {db_revision}")

    if len(heads) != 1:
        errors.append(f"Expected exactly one alembic head, found {len(heads)}: {heads}")

    if db_revision is None:
        errors.append("Database has no alembic_version table or no revision recorded.")
    else:
        revision = script.get_revision(db_revision)
        if revision is None:
            errors.append(
                f"Database revision {db_revision} is not present in the repo revision map."
            )

    if errors:
        print("\nERRORS:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nOK: alembic heads and DB revision are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
