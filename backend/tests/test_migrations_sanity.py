from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from backend.app.db import Base


ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _load_script() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    return ScriptDirectory.from_config(config)


def test_alembic_single_head():
    script = _load_script()
    heads = script.get_heads()
    assert len(heads) == 1


def test_alembic_revision_graph_has_no_gaps():
    script = _load_script()
    head = script.get_heads()[0]
    assert script.get_revision(head) is not None


def test_alembic_db_revision_known(tmp_path):
    db_path = tmp_path / "alembic.db"
    database_url = f"sqlite:///{db_path}"
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    command.stamp(config, "head")

    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()

    script = _load_script()
    assert revision is not None
    assert script.get_revision(revision) is not None


def test_sqlite_bootstrap_creates_tables(tmp_path):
    db_path = tmp_path / "bootstrap.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "businesses" in tables
