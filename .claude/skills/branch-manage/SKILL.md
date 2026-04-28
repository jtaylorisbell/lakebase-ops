---
name: branch-manage
description: Create, reset, delete, or list Lakebase dev branches.
trigger: User asks to create, reset, delete, or list dev branches, or mentions branch management.
---

# Branch Management

Manage Lakebase Postgres dev branches via Makefile targets that wrap `databricks postgres`.

## Operations

### Create a branch

```bash
make branch-create NAME=dev-{first-last}
```

This forks from `production`, creates a `primary` read-write endpoint, **and** provisions the calling user's OAuth Postgres role on the new branch. After creation, run migrations on the new branch:

```bash
LAKEBASE_BRANCH_ID=dev-{first-last} uv run alembic upgrade head
```

There's no Data API anymore — nothing else to enable.

### Reset a branch

```bash
make branch-reset NAME=dev-{first-last}
LAKEBASE_BRANCH_ID=dev-{first-last} uv run alembic upgrade head
```

### Delete a branch

```bash
make branch-delete NAME=dev-{first-last}
```

Confirm with the user before deleting — irreversible.

### List branches

```bash
make branch-list
```

## Conventions

- Branch naming: `dev-{first-last}` derived from email prefix (`taylor.isbell@…` → `dev-taylor-isbell`)
- `production` is the default and should never be deleted or reset manually
- `LAKEBASE_BRANCH_ID` env var targets a specific branch for migrations and the backend
- `.env` should have `DATABRICKS_CONFIG_PROFILE=todo-app-dev`
