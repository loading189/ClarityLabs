from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/claritylabs"
engine = create_engine(DB_URL)

with engine.begin() as conn:
    exists = conn.execute(text("""
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_schema='public' AND table_name='alembic_version'
        )
    """)).scalar()

    print("alembic_version table exists:", bool(exists))

    if exists:
        v = conn.execute(text("select version_num from alembic_version")).scalar()
        print("DB says current revision:", v)
