# lakebase-ops

A reference repository for deploying and maintaining a **Databricks Lakebase Autoscaling** project on **Azure**, using Terraform for infrastructure provisioning, Databricks Asset Bundles for app deployment, Alembic for Postgres migrations, and Python scripts for role and branch management.

> **Lakebase Autoscaling** is currently in Beta in: `eastus2`, `westeurope`, `westus`.

All scripts and migrations use **Databricks SDK OAuth** for credential resolution — PGHOST, PGUSER, and PGPASSWORD are auto-resolved from your authenticated SDK session and only need to be set explicitly if you want to bypass the SDK.

---

## Repository Structure

```
lakebase-ops/
├── README.md                        # ← you are here
├── Makefile                         # Common workflow commands
├── .env.example                     # Environment variable template
│
├── terraform/                       # Infrastructure provisioning (Terraform)
│   ├── providers.tf
│   ├── variables.tf
│   ├── terraform.tfvars.example
│   ├── project.tf                   # Lakebase project + default branch
│   ├── branches.tf                  # Dev / staging branches + endpoints
│   ├── permissions.tf               # Project ACLs (CAN_USE / CAN_MANAGE)
│   └── outputs.tf
│
├── alembic.ini                      # Alembic config (at project root)
├── alembic/                         # Database migrations (SDK OAuth via LakebaseSettings)
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
└── scripts/                         # Operational Python helpers
    ├── helpers.py                   # Shared connection / auth utilities (SDK OAuth)
    ├── manage_roles.py              # Create & grant Postgres roles (users + SPs)
    └── manage_branches.py           # Create, list, reset branches via SDK
```

---

## Prerequisites

| Tool | Minimum Version | Purpose |
|---|---|---|
| [Terraform](https://developer.hashicorp.com/terraform/install) | 1.5+ | Infrastructure provisioning |
| [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install) | 0.287.0+ | App deployment (DABs), auth tokens |
| [uv](https://docs.astral.sh/uv/) | 0.4+ | Python package management, script runner |
| Python | 3.10+ | Alembic migrations, helper scripts |
| psql *(optional)* | 15+ | Ad-hoc Postgres access |

```bash
# Authenticate to your Azure Databricks workspace
databricks auth login --host https://<workspace>.azuredatabricks.net
```

---

## Quick Start

```bash
# 1. Clone & install
git clone <repo-url> && cd lakebase-ops
cp .env.example .env           # fill in your values
uv sync

# 2. Provision infrastructure
make tf-apply                  # Terraform: project, branches, endpoints, ACLs

# 3. Manage roles
make roles                     # creates Postgres roles & grants

# 4. Run migrations
make migrate                   # runs Alembic against production branch

# 5. Create a dev branch & migrate it
make branch-create NAME=dev/alex
make migrate BRANCH=dev/alex
```

---

## 1 · Environment Variables

Create `.env` from the template. The Makefile and scripts source this file.

> **Note:** PGHOST, PGUSER, and PGPASSWORD are **optional** — when unset, scripts and migrations auto-resolve them via the Databricks SDK using your OAuth session. Set them explicitly only to bypass SDK resolution (e.g., for connecting to a specific host directly).

```bash
# .env.example

# ── Azure Databricks ─────────────────────────────
DATABRICKS_HOST=https://<workspace>.azuredatabricks.net

# ── Lakebase project settings ────────────────────
LAKEBASE_PROJECT_ID=my-app
LAKEBASE_PROJECT_DISPLAY_NAME="My Application"
LAKEBASE_PG_VERSION=17
LAKEBASE_REGION=eastus2

# ── Branch / endpoint defaults ───────────────────
LAKEBASE_BRANCH_ID=production
LAKEBASE_ENDPOINT_ID=primary
LAKEBASE_DEFAULT_MIN_CU=0.5
LAKEBASE_DEFAULT_MAX_CU=2

# ── Postgres connection (optional — auto-resolved via SDK) ─
# PGHOST=
# PGPORT=5432
# PGDATABASE=databricks_postgres
# PGUSER=                   # your Databricks email (auto-detected)
# PGPASSWORD=               # OAuth token (auto-generated via SDK)

# ── Team members to provision ────────────────────
TEAM_ANALYSTS='["analyst1@company.com","analyst2@company.com"]'
TEAM_ENGINEERS='["eng1@company.com","eng2@company.com"]'
```

---

## 2 · Provisioning with Terraform

### `terraform/providers.tf`

```hcl
terraform {
  required_version = ">= 1.5"

  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.65.0"
    }
  }
}

provider "databricks" {
  # Reads DATABRICKS_HOST + cached OAuth automatically.
  # Or set: host, token, azure_workspace_resource_id, etc.
}
```

### `terraform/variables.tf`

```hcl
# ── Project ──────────────────────────────────────
variable "project_id" {
  description = "Immutable resource ID for the Lakebase project (lowercase, hyphens, 1-63 chars)."
  type        = string
  default     = "my-app"
}

variable "project_display_name" {
  description = "Human-readable display name shown in the Lakebase App."
  type        = string
  default     = "My Application"
}

variable "pg_version" {
  description = "Postgres major version."
  type        = number
  default     = 17
}

# ── Branches ─────────────────────────────────────
variable "extra_branches" {
  description = "Map of additional long-lived branches to create beneath the default production branch."
  type = map(object({
    min_cu    = number
    max_cu    = number
    no_expiry = bool
  }))
  default = {
    development = { min_cu = 0.5, max_cu = 2, no_expiry = true }
    staging     = { min_cu = 0.5, max_cu = 4, no_expiry = true }
  }
}

# ── Permissions ──────────────────────────────────
variable "manage_users" {
  description = "List of Databricks user emails to grant CAN_MANAGE on the project."
  type        = list(string)
  default     = []
}

variable "use_users" {
  description = "List of Databricks user emails to grant CAN_USE on the project."
  type        = list(string)
  default     = []
}

variable "manage_groups" {
  description = "List of Databricks group names to grant CAN_MANAGE on the project."
  type        = list(string)
  default     = []
}

variable "use_groups" {
  description = "List of Databricks group names to grant CAN_USE on the project."
  type        = list(string)
  default     = []
}
```

### `terraform/project.tf`

```hcl
# ── Lakebase project ────────────────────────────
# Creating the project automatically provisions:
#   • a "production" branch (the root / default branch)
#   • a read-write endpoint on that branch

resource "databricks_postgres_project" "this" {
  project_id   = var.project_id
  display_name = var.project_display_name
  pg_version   = var.pg_version
}
```

### `terraform/branches.tf`

```hcl
# ── Additional long-lived branches ───────────────
# Each branch gets its own read-write endpoint for
# independent development / staging work.

resource "databricks_postgres_branch" "extra" {
  for_each = var.extra_branches

  parent    = databricks_postgres_project.this.id # parent = production
  branch_id = each.key
  no_expiry = each.value.no_expiry
}

resource "databricks_postgres_endpoint" "extra" {
  for_each = var.extra_branches

  parent                   = databricks_postgres_branch.extra[each.key].id
  endpoint_id              = "primary"
  endpoint_type            = "ENDPOINT_TYPE_READ_WRITE"
  autoscaling_limit_min_cu = each.value.min_cu
  autoscaling_limit_max_cu = each.value.max_cu
}
```

### `terraform/permissions.tf`

```hcl
# ── Project-level ACLs ──────────────────────────
# CAN_MANAGE → create/delete branches, manage computes, manage roles
# CAN_USE    → view resources, get connection URI, limited branch ops
#
# NOTE: This controls *platform* permissions only.
# Postgres database-level permissions (GRANT/REVOKE) are managed
# separately via scripts/manage_roles.py.

resource "databricks_permissions" "project" {
  database_project_name = databricks_postgres_project.this.project_id

  # ── CAN_MANAGE for individual users ────────────
  dynamic "access_control" {
    for_each = var.manage_users
    content {
      user_name        = access_control.value
      permission_level = "CAN_MANAGE"
    }
  }

  # ── CAN_USE for individual users ───────────────
  dynamic "access_control" {
    for_each = var.use_users
    content {
      user_name        = access_control.value
      permission_level = "CAN_USE"
    }
  }

  # ── CAN_MANAGE for groups ──────────────────────
  dynamic "access_control" {
    for_each = var.manage_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_MANAGE"
    }
  }

  # ── CAN_USE for groups ─────────────────────────
  dynamic "access_control" {
    for_each = var.use_groups
    content {
      group_name       = access_control.value
      permission_level = "CAN_USE"
    }
  }
}
```

### `terraform/outputs.tf`

```hcl
output "project_name" {
  description = "Full resource name of the Lakebase project."
  value       = databricks_postgres_project.this.id
}

output "branch_ids" {
  description = "Map of branch key → full resource name."
  value = {
    for k, b in databricks_postgres_branch.extra : k => b.id
  }
}

output "endpoint_ids" {
  description = "Map of branch key → endpoint resource name."
  value = {
    for k, e in databricks_postgres_endpoint.extra : k => e.id
  }
}
```

### `terraform/terraform.tfvars.example`

```hcl
project_id           = "my-app"
project_display_name = "My Application"
pg_version           = 17

extra_branches = {
  development = { min_cu = 0.5, max_cu = 2, no_expiry = true }
  staging     = { min_cu = 0.5, max_cu = 4, no_expiry = true }
}

manage_groups = ["Engineering"]
use_groups    = ["Data Analysts"]
manage_users  = ["lead@company.com"]
use_users     = ["analyst@company.com"]
```

### Usage

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit values
terraform init
terraform plan
terraform apply
```

---

## 3 · Database Migrations with Alembic

Alembic manages Postgres schema changes as versioned Python files. The `alembic/env.py` uses `LakebaseSettings` from the application to resolve credentials via the Databricks SDK — no hardcoded connection strings needed. It also auto-creates the application database if it doesn't exist.

### Running Migrations

```bash
# Against the default branch (auto-resolved via SDK)
uv run alembic upgrade head

# Against a specific branch — override via env var:
LAKEBASE_BRANCH_ID=dev/alex uv run alembic upgrade head

# Generate a new migration from model changes:
uv run alembic revision --autogenerate -m "add_audit_log_table"

# Show current version:
uv run alembic current

# Downgrade one step:
uv run alembic downgrade -1
```

---

## 4 · Postgres Role Management

Lakebase has **two independent permission layers**:

1. **Project ACLs** (CAN_USE / CAN_MANAGE) — managed via Terraform or the SDK.
   Controls platform actions: creating branches, managing computes, etc.

2. **Postgres roles & GRANTs** — managed via SQL.
   Controls data access: SELECT, INSERT, schema creation, etc.

These are **not automatically synchronised**. The scripts below handle layer 2. Dependencies (`databricks-sdk`, `psycopg2-binary`, etc.) are managed in `pyproject.toml` — run `uv sync` to install.

### `scripts/helpers.py`

The helpers module uses the Databricks SDK for credential resolution instead of relying on raw environment variables or subprocess-based token refresh. It resolves host, user, and password via `w.postgres.get_endpoint()` and `w.postgres.generate_database_credential()`, falling back to PGHOST/PGUSER/PGPASSWORD when set.

### `scripts/manage_roles.py`

```bash
# Create roles from .env TEAM_* arrays
uv run python scripts/manage_roles.py --from-env

# Or specify users directly
uv run python scripts/manage_roles.py --engineers eng1@co.com eng2@co.com
uv run python scripts/manage_roles.py --analysts analyst1@co.com
uv run python scripts/manage_roles.py --readonly reader@co.com

# CI/CD: create SERVICE_PRINCIPAL roles for the CI SP and App SP
uv run python scripts/manage_roles.py --app lakebase-todo-app-dev
```

### `scripts/manage_branches.py`

```bash
# List all branches
uv run python scripts/manage_branches.py list

# Create a dev branch (from production by default)
uv run python scripts/manage_branches.py create dev/alex

# Create from a specific parent with custom CU limits
uv run python scripts/manage_branches.py create dev/alex --parent development --min-cu 0.5 --max-cu 2

# Reset a branch (re-sync from parent)
uv run python scripts/manage_branches.py reset dev/alex

# Delete a branch
uv run python scripts/manage_branches.py delete dev/alex
```

---

## 5 · Makefile

All Makefile targets use `uv run` for Python and Alembic commands.

```makefile
# ── Terraform ────────────────────────────────────
make tf-init          # terraform init
make tf-plan          # terraform plan
make tf-apply         # terraform apply -auto-approve
make tf-destroy       # terraform destroy -auto-approve

# ── Databricks Asset Bundles (App) ───────────────
make dab-validate     # databricks bundle validate
make dab-deploy       # databricks bundle deploy

# ── Roles ────────────────────────────────────────
make roles            # create Postgres roles from .env TEAM_* arrays
make roles-app APP_NAME=my-app-dev  # create SP roles for CI + App

# ── Migrations ───────────────────────────────────
make migrate           # uv run alembic upgrade head
make migrate-status    # uv run alembic current
make migrate-downgrade # uv run alembic downgrade -1
make migrate-new       # create a new migration (prompts for message)

# ── Branches ─────────────────────────────────────
make branch-list              # list all branches
make branch-create NAME=dev/alex  # create a branch
make branch-reset NAME=dev/alex   # reset from parent
make branch-delete NAME=dev/alex  # delete a branch
```

---

## 6 · Recommended Workflow

### Initial Setup (one-time)

```
1.  terraform apply          # Provision project, branches, ACLs
2.  make roles               # Create Postgres roles for team
3.  make migrate             # Apply schema to production branch
```

### Daily Development

```
1.  make branch-create NAME=dev/alex          # isolated branch
2.  LAKEBASE_BRANCH_ID=dev/alex make migrate  # apply schema
3.  ... develop & test ...
4.  make branch-reset NAME=dev/alex           # pull latest from parent
```

### Promoting a Migration

```
1.  Write & test migration on dev branch
2.  PR review the new file in migrations/alembic/versions/
3.  CI runs: make migrate (against staging branch)
4.  After merge: make migrate (against production)
```

### Permission Model Cheat Sheet

| Layer | What it controls | Managed by |
|---|---|---|
| Project ACLs | Platform ops (branches, computes, settings) | `terraform/permissions.tf` |
| Postgres roles | Data access (SELECT, INSERT, schema creation) | `scripts/manage_roles.py` |

These two layers are **independent** — granting CAN_MANAGE does not automatically give database access, and vice versa.

---

## 7 · Key Concepts for Postgres Newcomers

**Roles vs Users** — In Postgres, a "user" is just a role with LOGIN privilege. Lakebase creates OAuth-authenticated roles via `databricks_create_role()`.

**Schemas** — A schema is a namespace inside a database. The default is `public`. You can create additional schemas (e.g., `analytics`, `staging`) and grant access independently.

**GRANTs are cumulative** — Permissions add up. `REVOKE` removes them. There is no "deny" — if any role grants access, the user has it.

**DEFAULT PRIVILEGES** — Regular `GRANT` only covers *existing* objects. Use `ALTER DEFAULT PRIVILEGES` so that future tables/sequences created in a schema automatically inherit the grants.

**Branches are copy-on-write** — Creating a branch is instant and doesn't duplicate data. Changes on a branch are isolated until you promote them (apply the same migration upstream).

---

## References

- [Lakebase Autoscaling API guide](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/api-usage)
- [Grant user access tutorial](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/grant-user-access-tutorial)
- [Branch-based dev workflow](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/dev-workflow-tutorial)
- [Terraform: databricks_permissions](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/permissions)
- [Terraform: databricks_postgres_project](https://registry.terraform.io/providers/databricks/databricks/latest/docs/resources/postgres_project)
- [Alembic documentation](https://alembic.sqlalchemy.org/)
