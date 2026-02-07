# Developer Database Guide

This repo uses Alembic for migrations and SQLAlchemy for runtime DB access. These tools are wired so that drift (missing revisions, multiple heads, or stale local DBs) fails fast.

## Quick commands

```bash
python -m backend.scripts.db_sanity
python -m backend.scripts.dev_reset_db --yes
pytest -q
```

## Local Postgres (no Docker required)

Use any local Postgres install you prefer. Ensure the DB URL matches your environment variables:

```bash
export DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/claritylabs
```

## Optional Docker Compose

If you do want Docker, use the included compose file:

```bash
docker compose up -d
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/claritylabs
```

## Resetting the local DB

This is destructive and intended for local development only:

```bash
python -m backend.scripts.dev_reset_db --yes
```

Add `--seed` to create a minimal demo business row.

## Sanity-check migrations

```bash
python -m backend.scripts.db_sanity
```

This prints the configured SQLAlchemy URL (password redacted), Alembic heads in the repo, and the database’s recorded `alembic_version`. If the repo has multiple heads or the database revision is unknown, it exits non-zero.

## Common errors

- **“Can’t locate revision”**: The DB’s `alembic_version` doesn’t exist in the repo revision map. Reset the DB or stamp to the correct revision.
- **“Database is being accessed by other users”**: Use `dev_reset_db --yes`, which terminates active connections before dropping.
- **Port mismatch (5432 vs 5433)**: Ensure the port in `DATABASE_URL` matches your Postgres instance.
