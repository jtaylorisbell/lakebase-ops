# `lbctl` — Lakebase role management

`lbctl` is installed automatically via `uv sync` and manages the database-layer permissions that no existing tool covers — OAuth role creation via `databricks_create_role()`, Postgres grants, and Data API authenticator setup.

## Commands

### `roles diff`

Show what's drifted between `db/roles.yml` and live Postgres. Exits with code 1 if changes are detected (CI-friendly).

```bash
uv run lbctl roles diff --config db/roles.yml
```

### `roles sync`

Sync live Postgres roles to match the desired config. Creates missing roles, upgrades/downgrades permissions, and adds authenticator grants.

```bash
# Sync roles to match desired state (CI/CD usage)
uv run lbctl roles sync --config db/roles.yml --app lakebase-todo-app-dev

# Preview changes without applying
uv run lbctl roles sync --config db/roles.yml --dry-run

# Revoke roles not in config
uv run lbctl roles sync --config db/roles.yml --revoke
```

### `roles provision`

Ad-hoc imperative provisioning — useful for one-off grants without editing `db/roles.yml`.

```bash
# Developer roles (read-write)
uv run lbctl roles provision --engineers dev1@co.com --engineers dev2@co.com

# Read-only roles
uv run lbctl roles provision --readonly analyst@co.com

# App service principal
uv run lbctl roles provision --app lakebase-todo-app-dev
```

## What each role gets

- `CONNECT` on `databricks_postgres`
- `USAGE` (+ `CREATE` for readwrite) on `public` schema
- `ALL PRIVILEGES` on all tables (readwrite) or `SELECT` only (readonly)
- `USAGE, SELECT` on all sequences
- `ALTER DEFAULT PRIVILEGES` for future objects
- `GRANT TO authenticator` for Data API access (if enabled)
