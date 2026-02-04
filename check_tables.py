from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/claritylabs"
engine = create_engine(DB_URL)

def has_table(conn, name: str) -> bool:
    return bool(conn.execute(text("""
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_schema='public' AND table_name=:name
        )
    """), {"name": name}).scalar())

with engine.begin() as conn:
    print("health_signal_states exists:", has_table(conn, "health_signal_states"))
    print("audit_logs exists:", has_table(conn, "audit_logs"))
