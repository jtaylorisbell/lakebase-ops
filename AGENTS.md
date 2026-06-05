# For agents adapting this repo

Read this first. It's the canonical map for using this repo as a starting point for a new Databricks App backed by Lakebase Autoscaling.

## What you get for free

- **Databricks App + Lakebase wiring.** `databricks.yml` plus `resources/*.yml` provision a Lakebase project, bind the App SP to it via `CAN_CONNECT_AND_CREATE`, and inject runtime config through `app.config.env`. Single `databricks bundle deploy + run` lifecycle.
- **OAuth-authenticated Postgres.** `src/backend/config.py` resolves the Lakebase host and refreshes Databricks-generated OAuth tokens (`src/backend/db/session.py` rewrites the password on each SQLAlchemy connect).
- **Schema-owned-by-app migrations.** Alembic runs on App startup. Whatever the App SP runs in `alembic upgrade head` lands in a schema the SP owns, which is the only thing CAN_CONNECT_AND_CREATE lets it read/write. `alembic/env.py` creates the schema before migrations.
- **Branching.** `make branch-create NAME=<anything>` forks a copy-on-write branch from production and provisions your OAuth Postgres role on it in one command. Branches are free, so use them per dev, per feature, per experiment.
- **React + Vite + TanStack Query frontend.** `frontend/` is a fully wired SPA that talks to `/api/*` via the existing client.
- **CI/CD.** `.github/workflows/deploy-dev.yml` deploys on every push to `main`; `release-prod.yml` is a manual prod release.
- **Lakebase CDF readiness.** Migration `0002` sets `REPLICA IDENTITY FULL` on every existing app table and defines the helper function in the app schema. A separate post-deploy step (`make install-cdf-trigger`, wired into CI) registers the global `CREATE TABLE` event trigger as the project owner so future tables auto-apply REPLICA IDENTITY FULL without the App SP needing superuser. Starting the actual feed is a workspace-UI step; see the section at the bottom of this file.

## Customizing this for your app

Five things to change. Everything else is the pattern. Don't touch it.

1. **`databricks.yml` bundle variables.** Flip the defaults for `lakebase_project_id`, `lakebase_schema`, optionally `lakebase_display_name`, and the bundle's `bundle.name`. These flow into the Lakebase project resource, the App SP's CAN_CONNECT_AND_CREATE binding, and the runtime `LAKEBASE_*` env vars via `resources/todo_app.yml`'s `app.config.env`.
2. **`.env`** (local dev only). Set `LAKEBASE_PROJECT_ID`, `LAKEBASE_BRANCH_ID`, and `LAKEBASE_SCHEMA` to match the new bundle defaults. See `.env.example`.
3. **Replace the Todo example entity.** It's the worked example, not the pattern. Files to delete or replace:
   - `alembic/versions/0001_initial_schema.py`: the `todos` table DDL
   - `src/backend/db/schemas.py`: `Todo` ORM model
   - `src/backend/db/crud.py`: `create_todo`, etc.
   - `src/backend/api/schemas.py`: `CreateTodoRequest`, `TodoResponse`, etc.
   - `src/backend/api/main.py`: `/api/todos`, `/api/stats` routes (keep `/api/health` and `/api/me`)
   - `src/backend/core/models.py`: `Priority` enum (Todo-specific)
   - `frontend/src/App.tsx`, `frontend/src/types/api.ts`, `frontend/src/api/client.ts`: frontend Todo UI/types/client
4. **Add your domain entities.** Follow the `add-entity` skill (`.claude/skills/add-entity/SKILL.md`). It walks the 7-file pattern: migration → ORM model → CRUD → Pydantic schemas → FastAPI routes → TS types → frontend client.
5. **Update branding.** `README.md`, `pyproject.toml` `[project] description`, the bundle's `lakebase_display_name`. Skim for "Todo" mentions.

## Don't touch these. They're the contract

- **`CAN_CONNECT_AND_CREATE` on the postgres app resource.** This is the entire reason migrations can run on startup without manual role provisioning. Don't downgrade to `CAN_CONNECT_AND_USE` or remove the binding.
- **The `${resources.postgres_projects.todo_app_project.project_id}` reference in `resources/todo_app.yml`.** Reverting that to a bare `${var.lakebase_project_id}` breaks the implicit Terraform dependency and first-time deploys race the branch.
- **The OAuth refresh in `src/backend/db/session.py`** (`event.listens_for(engine, "do_connect")` rewrites the password on each new connection). Without it the connection works for ~1 hour, then dies.
- **Alembic running at startup** in `resources/todo_app.yml`'s `command:` block. Migrations *must* execute as the App SP. That's how it ends up owning the schema.
- **The `{"schema": SCHEMA}` in `__table_args__`** on every ORM model. Defaults to `public`, where the App SP has no permissions.
- **`LAKEBASE_PROJECT_ID`, `LAKEBASE_BRANCH_ID`, `LAKEBASE_SCHEMA` are required fields** (pydantic raises on missing). Don't add silent defaults in code; the bundle injects them for deploy, `.env` provides them for local.

## Operational primitives

Branches are copy-on-write and free. `NAME` can be anything: `dev-taylor`, `feature-payments`, `repro-incident-1234`. Use them like git branches.

- `make branch-create NAME=<anything>`: fork a branch off `production` + provision your OAuth role
- `make branch-reset NAME=<anything>`: reset a branch to its fork point
- `make branch-delete NAME=<anything>`: delete a branch when you're done with it
- `make migrate`: run alembic against `$BRANCH` (defaults to `production`)
- `make role-create BRANCH=<anything>`: provision the caller's OAuth role on a branch (idempotent: errors with BadRequest if it exists)
- `databricks bundle deploy -t dev` / `databricks bundle run -t dev todo_app`: deploy + start the app
- `make install-cdf-trigger`: register the global event trigger so future tables auto-get REPLICA IDENTITY FULL (must run as a project owner; CI does this automatically after `bundle run`)
- `uv run uvicorn app:app --host 0.0.0.0 --port 8000`: backend dev server (reads `.env`)
- `cd frontend && npm run dev`: frontend dev server (proxies `/api` to 8000)

## Common pitfalls

- **First deploy needs the Lakebase project's `production` branch to exist before the app binding resolves.** The implicit dependency via `${resources.postgres_projects.*.project_id}` handles this; leave it.
- **`bundle destroy` tombstones the Lakebase project id** for an extended window. The slot stays reserved even though the project disappears from the UI and `list-projects`. Rename via `var.lakebase_project_id` if you need to redeploy quickly.
- **The auto-created Lakebase database is addressable as `databricks-postgres` (hyphen)** in the app resource binding. The Postgres database *name* used in connection strings is `databricks_postgres` (underscore). Two different namespaces, both correct.
- **Don't put DDL outside alembic.** The App SP can only touch objects it created via migrations.

## Layout

```
.
├── AGENTS.md                  # ← you are here
├── README.md                  # human-oriented overview
├── app.py                     # Databricks Apps entry point
├── databricks.yml             # DAB: bundle name, vars, sync, target ACLs
├── resources/
│   ├── lakebase.yml           # Lakebase project resource
│   └── todo_app.yml           # App resource: inline cmd/env + CAN_CONNECT_AND_CREATE
├── pyproject.toml             # uv project; module name = `backend` via tool.uv.build-backend
├── uv.lock                    # pinned deps required by Databricks Apps
├── alembic/                   # migrations; env.py creates LAKEBASE_SCHEMA before running
├── src/backend/               # Python package (FastAPI + SQLAlchemy + Lakebase auth)
│   ├── config.py              # LakebaseSettings, OAuth token manager, SCHEMA
│   ├── api/                   # FastAPI routes, request/response schemas, current-user
│   ├── core/models.py         # domain enums
│   └── db/                    # SQLAlchemy session, ORM models, CRUD
└── frontend/                  # React + Vite + TanStack Query
```

## Enabling Lakebase CDF

The repo handles the Postgres-side prep automatically:

- Alembic migration `0002` (runs on every App startup as the App SP) sets `REPLICA IDENTITY FULL` on every app-owned table and defines `"{LAKEBASE_SCHEMA}".set_full_replica_identity()`.
- `make install-cdf-trigger` (or the equivalent CI step in `deploy-dev.yml` / `release-prod.yml`) runs as the project owner and registers a global `CREATE TABLE` event trigger. After it runs once, every future `CREATE TABLE` automatically gets `REPLICA IDENTITY FULL` — including tables alembic adds later.

Three things still need to happen outside the repo before changes flow to Unity Catalog:

1. **Workspace preview.** A workspace admin enables the **Lakebase Change Data Feed** preview from the workspace Previews page.
2. **Destination UC perms.** The identity starting CDF needs `USE CATALOG`, `USE SCHEMA`, and `CREATE TABLE` on the destination Unity Catalog catalog and schema, plus `CAN MANAGE` on the Lakebase project. Project owners already have `CAN MANAGE`.
3. **Start the feed.** In the workspace: open **Lakebase Postgres** (app switcher) → your project → branch → **Change Data Feed** tab → **Start**. Pick the source schema (`LAKEBASE_SCHEMA`) and the destination UC catalog + schema.

Tables show up in Unity Catalog as `lb_<table_name>_history` Delta tables, batched ~every 15s. Inspect feed state from Postgres with:

```sql
SELECT * FROM wal2delta.tables;
```

Updates produce two rows (`update_preimage` + `update_postimage`); deletes produce one (`delete`). See the [Lakebase CDF doc](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/lakebase-cdf) for the destination schema and downstream patterns (materialized views, Spark Declarative Pipelines, Structured Streaming `foreachBatch`).

**Limitations to know.** Source must be `databricks_postgres` (this repo already uses it). Partitioned tables aren't supported. Empty tables are skipped until they have at least one row. Destination catalogs configured with default storage aren't supported.
