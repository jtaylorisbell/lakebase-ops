---
name: onboard-developer
description: Onboard a new developer to the Lakebase Todo App — adds platform permissions.
trigger: User asks to onboard, add, or invite a new developer or team member.
---

# Onboard Developer

Add a new developer by editing `databricks.yml`. CI deploys the platform permission on the next push to `main`. There is no separate database-role config — developers create their own Postgres role when they create a dev branch (`make branch-create`).

## Steps

1. **Collect info**: ask for the developer's Databricks email.

2. **Edit `databricks.yml`** — append a `user_name` entry under `permissions:` for **each target** (`dev` and `prod`):

```yaml
targets:
  dev:
    resources:
      postgres_projects:
        todo_app_project:
          permissions:
            - user_name: existing@databricks.com
              level: CAN_MANAGE
            - user_name: NEW_EMAIL          # ← add here
              level: CAN_MANAGE
```

Validate the email isn't already in either target's permissions block.

3. **Summarize and remind**:
   - Push to `main` for CI to deploy (`databricks bundle deploy -t dev`).
   - After CI completes, the new dev follows the local-dev steps in `README.md`:
     1. `databricks auth login --profile todo-app-dev`
     2. `make branch-create NAME=dev-{first-last}` (also provisions their Postgres role)
     3. `LAKEBASE_BRANCH_ID=dev-{first-last} uv run alembic upgrade head`
     4. Start backend + frontend

## Validation

- No duplicate emails per target
- Email format: must contain `@`
- Same email should usually appear in both `dev` and `prod` targets
