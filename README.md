# Lakebase Todo App

A reference for running a full-stack app (FastAPI + React) on Databricks Apps backed by Lakebase Autoscaling. Everything is wired through Databricks Asset Bundles, OAuth, and the standard Databricks CLI. No PATs, no custom CLI, no Data API.

## Architecture

```
┌─────────────────────────────────┐
│         Databricks App          │
│  ┌──────────┐  ┌─────────────┐  │
│  │  React   │──│   FastAPI   │  │
│  │ Frontend │  │  + psycopg  │  │
│  └──────────┘  └──────┬──────┘  │
└────────────────────────┼────────┘
                         │ OAuth-authenticated Postgres
                         ▼
              ┌─────────────────────────────┐
              │      Lakebase Postgres      │
              │  ┌───────────────────────┐  │
              │  │  production           │  │  ← deployed app
              │  ├───────────────────────┤  │
              │  │  dev-taylor           │  │  ← branches per dev,
              │  │  feature-payments     │  │     feature, experiment.
              │  │  repro-incident-1234  │  │     creation is free.
              │  └───────────────────────┘  │
              └─────────────────────────────┘
```

The app talks to Lakebase over a direct Postgres connection authenticated by an OAuth token generated from the Databricks SDK. The token is refreshed transparently.

## Repository layout

```
lakebase-todo-app/
├── app.py                    # Databricks Apps entry point (imports FastAPI app)
├── databricks.yml            # DAB: bundle vars, sync, target ACLs
├── resources/
│   ├── lakebase.yml          # Lakebase project resource
│   └── todo_app.yml          # App resource: inline command/env + CAN_CONNECT_AND_CREATE on Lakebase
├── pyproject.toml            # Python deps (uv); replaces requirements.txt
├── uv.lock                   # Pinned deps required by Databricks Apps
├── alembic/                  # Schema migrations (creates the `LAKEBASE_SCHEMA` schema)
├── src/backend/              # Python package (FastAPI + SQLAlchemy + Lakebase auth)
│   ├── config.py             # LakebaseSettings, auto-resolves host/user/token
│   ├── api/                  # FastAPI routes
│   └── db/                   # SQLAlchemy session, models, CRUD
└── frontend/                 # React + Vite + Tailwind
```

## How permissions work

The App SP gets database access automatically through the bundle's app resource:

```yaml
# resources/todo_app.yml
resources:
  apps:
    todo_app:
      resources:
        - name: postgres
          postgres:
            branch: projects/${var.lakebase_project_id}/branches/${var.lakebase_branch}
            database: projects/${var.lakebase_project_id}/branches/${var.lakebase_branch}/databases/${var.lakebase_database_id}
            permission: CAN_CONNECT_AND_CREATE
```

Project id, branch, and database id are bundle variables defined in `databricks.yml`, so the project name lives in exactly one place and flows into both the resource binding and the app's `LAKEBASE_PROJECT_ID` env var.

`CAN_CONNECT_AND_CREATE` lets the App SP connect and create new schemas/tables, but only gives it read/write access to objects it owns. So **all schema and table creation is in alembic migrations** that run as the App SP at startup (`uv run alembic upgrade head && uv run uvicorn …`, defined inline in `resources/todo_app.yml`). The App ends up owning the schema named by `LAKEBASE_SCHEMA` (default `todo_app`) and everything in it.

For human developers, OAuth Postgres roles are created on-demand with `databricks postgres create-role` (see [Local development](#local-development) below). There is no separate role config to keep in sync.

## Local development

Prerequisites: `uv`, `databricks` CLI ≥ 0.297, Node 20+.

1. **Authenticate** (once per workspace):
   ```bash
   databricks auth login --host https://<workspace> --profile todo-app-dev
   ```
   Add to `.env`:
   ```
   DATABRICKS_CONFIG_PROFILE=todo-app-dev
   ```

2. **Get platform access.** An admin adds you to the `permissions` block under each target in `databricks.yml` and runs `databricks bundle deploy`. This grants you `CAN_MANAGE` on the Lakebase project so you can create branches.

3. **Create a branch.** Fork one off `production` and provision your OAuth Postgres role on it. Branches are copy-on-write and free, so `NAME` can be anything: per dev, per feature, per experiment.
   ```bash
   make branch-create NAME=dev-<your-name>          # or feature-foo, repro-incident-1234, …
   ```

4. **Run migrations on your branch** (creates the `LAKEBASE_SCHEMA` you'll own):
   ```bash
   LAKEBASE_BRANCH_ID=dev-<your-name> uv run alembic upgrade head
   ```

5. **Start the servers**:
   ```bash
   uv run uvicorn app:app --host 0.0.0.0 --port 8000   # backend
   cd frontend && npm install && npm run dev            # frontend
   ```

   Backend on `:8000`, frontend on `:5173` (Vite proxies `/api` → backend).

### Branch / migration cheat sheet

```bash
make branch-list                        # list branches
make branch-create NAME=dev-foo         # fork from production + create endpoint + provision role
make branch-reset   NAME=dev-foo        # reset to fork point
make branch-delete  NAME=dev-foo

make migrate                            # alembic upgrade head against $BRANCH (default: production)
make migrate-status
make migrate-new                        # new empty revision
```

`LAKEBASE_BRANCH_ID` controls which branch the alembic + backend processes target. Set it in `.env` for local dev; the deployed app gets `LAKEBASE_BRANCH_ID=production` injected from the bundle's `var.lakebase_branch`.

## Deployment

CI uses a Databricks-managed service principal (`DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`).

- **deploy-dev.yml** runs on every push to `main`: `databricks bundle deploy -t dev` then `databricks bundle run -t dev todo_app`. Migrations run inside the App on startup.
- **release-prod.yml** is manual; runs tests then deploys to `prod` and tags a GitHub release.

## Lakebase Change Data Feed (CDF)

Migration `0002` prepares every app table for CDF by setting `REPLICA IDENTITY FULL` (required so updates and deletes carry the full pre- and post-row state in the WAL). It also tries to install a global `CREATE TABLE` event trigger so future tables get the same treatment automatically; the App SP lacks superuser, so the trigger usually skips with a `NOTICE`. The `add-entity` skill includes the explicit `ALTER` on new tables to cover that case.

Three things still need to happen outside the repo before changes flow to Unity Catalog:

1. A workspace admin enables the **Lakebase Change Data Feed** preview from the workspace Previews page.
2. The identity starting the feed needs `USE CATALOG`, `USE SCHEMA`, and `CREATE TABLE` on the destination Unity Catalog catalog/schema, plus `CAN MANAGE` on the Lakebase project.
3. In the workspace: open **Lakebase Postgres** → your project → branch → **Change Data Feed** → **Start**. Pick the source schema (`LAKEBASE_SCHEMA`) and the destination UC catalog + schema.

Captured tables show up as `lb_<table_name>_history` Delta tables, batched ~every 15s. Inspect feed state from Postgres with `SELECT * FROM wal2delta.tables;`. See the [Lakebase CDF doc](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/lakebase-cdf) for the destination schema, data type mapping, and downstream consumer patterns (materialized views, Spark Declarative Pipelines, Structured Streaming).

## References

- [Lakebase project Postgres roles](https://docs.databricks.com/aws/en/oltp/projects/postgres-roles)
- [Lakebase Change Data Feed](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/lakebase-cdf)
- [Databricks Apps resources](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)
- [Databricks Asset Bundles](https://docs.databricks.com/aws/en/dev-tools/bundles/)
- [Alembic](https://alembic.sqlalchemy.org/)
