---
name: roles-manage
description: Manage Postgres roles for the Lakebase Todo App via the Databricks CLI.
trigger: User asks about Postgres roles, grants, or database access for the Todo App.
---

# Postgres Role Management

Roles are managed directly with `databricks postgres` — there is no custom CLI or YAML config.

The App SP gets `CAN_CONNECT_AND_CREATE` automatically through the `postgres` resource declared in `resources/todo_app.yml`, so the App never needs a manual role.

The only thing that needs explicit role provisioning is a developer's OAuth role on a dev branch. `make branch-create` does this automatically as part of branch creation, but the underlying command is:

```bash
databricks postgres create-role projects/todo-app/branches/<branch> \
  --role-id <role-id> \
  --json '{"spec": {"identity_type": "USER", "postgres_role": "<email>"}}'
```

## Common operations

### Provision your own role on an existing branch

```bash
make role-create BRANCH=dev-<name>
```

`EMAIL` and `ROLE_ID` default to your `git config user.email`.

### List existing roles on a branch

```bash
databricks postgres list-roles projects/todo-app/branches/<branch>
```

### Inspect a role

```bash
databricks postgres get-role projects/todo-app/branches/<branch>/roles/<role-id>
```

### Delete a role

```bash
databricks postgres delete-role projects/todo-app/branches/<branch>/roles/<role-id>
```

## What developers can do once their role exists

- Connect to their dev branch as themselves over OAuth
- Run `alembic upgrade head` (creates the `todo_app` schema, owned by them)
- Read/write everything in that schema

The production branch is owned by the App SP — humans don't need roles there for day-to-day work.

## Reference

- [docs: Lakebase Postgres roles](https://docs.databricks.com/aws/en/oltp/projects/postgres-roles)
