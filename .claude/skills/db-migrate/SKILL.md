---
name: db-migrate
description: Run, create, check status, or rollback Alembic database migrations.
trigger: User asks about migrations, schema changes, alembic, or database schema.
---

# Database Migrations

Alembic migrations target a Lakebase Postgres branch. The deployed App runs `alembic upgrade head` automatically on startup (see `app.yaml`), so production usually doesn't need manual intervention. Local dev branches need manual migration runs.

`LAKEBASE_BRANCH_ID` controls which branch is targeted. When unset, the app derives it from the caller's identity (`production` for SP, `dev-{username}` for users).

Migrations create the `todo_app` schema and tables under it. The role running the migration becomes the owner of the schema, so on production the App SP owns everything (required by `CAN_CONNECT_AND_CREATE`).

## Operations

### Run pending migrations

```bash
LAKEBASE_BRANCH_ID={branch} uv run alembic upgrade head
```

Or `make migrate` (defaults to `BRANCH=production` from the Makefile).

### Check migration status

```bash
LAKEBASE_BRANCH_ID={branch} uv run alembic current
```

Or `make migrate-status`.

### Create a new migration

```bash
uv run alembic revision -m "description"                                 # empty template
LAKEBASE_BRANCH_ID={branch} uv run alembic revision --autogenerate -m "…" # diff against models
```

Migration files land in `alembic/versions/`.

### Downgrade

```bash
LAKEBASE_BRANCH_ID={branch} uv run alembic downgrade -1
```

Or `make migrate-downgrade`.

## Key details

- `alembic/env.py` resolves credentials via the Databricks SDK and creates the `todo_app` schema before running migrations
- The `alembic_version` table also lives in `todo_app` so the App SP owns it
- New tables in models must include `{"schema": SCHEMA}` in `__table_args__` (see `src/todo_app/db/schemas.py`)
