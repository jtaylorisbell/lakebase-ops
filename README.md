# 🏗️ Lakebase Ops — End-to-End Automation Reference

A complete, working reference for **automating Databricks Lakebase Autoscaling** — from infrastructure provisioning and CI/CD pipelines to developer onboarding and branch-based workflows. Built around a full-stack To-Do app (FastAPI + React) as the working example.

> ⚠️ **Lakebase Autoscaling** is in Beta in: `eastus2`, `westeurope`, `westus`.

## 🎯 What this repo demonstrates

Lakebase Autoscaling is new and there aren't established patterns for managing it in production. This repo solves that by providing a complete, working reference for:

- **🔧 Infrastructure as Code** — Databricks Asset Bundles provision the Lakebase project and platform ACLs alongside the app in a single declarative config
- **🚀 Automated CI/CD** — GitHub Actions deploys the app + infrastructure, creates Postgres roles for service principals, runs migrations, and ships code — all via OAuth (no PATs)
- **👥 Developer onboarding** — Add an email to `resources/lakebase.yml` + `scripts/db_access.json`, deploy, and the developer gets platform permissions + Postgres roles + Data API access
- **🌿 Branch-per-developer isolation** — Each developer gets a copy-on-write Lakebase branch forked from production, with auto-detection so no config is needed
- **🔐 Two-layer permission model** — Platform ACLs (DABs) and Postgres roles (SQL scripts) are managed independently and automated through CI
- **📡 Data API (PostgREST)** — The app uses the Lakebase Data API instead of direct Postgres connections, with authenticator role grants managed automatically

The To-Do app itself is intentionally simple — the real value is the operational scaffolding around it.

---

## 📂 Repository Structure

```
lakebase-todo-app/
├── app.py                           # Entrypoint (adds src/ to path, imports FastAPI app)
├── app.yaml                         # Databricks Apps runtime config
├── databricks.yml                   # DAB config (app + Lakebase infra)
├── resources/
│   ├── todo_app.yml                 # App resource definition
│   └── lakebase.yml                 # Lakebase project + platform ACLs
├── pyproject.toml                   # Python deps (uv)
├── Makefile                         # Common workflow shortcuts
│
├── src/todo_app/                    # 🐍 Backend (FastAPI + Data API)
│   ├── config.py                    # LakebaseSettings — auto-detects branch, user, endpoint
│   ├── api/                         # FastAPI routes
│   └── db/                          # Data API client (PostgREST), schemas
│
├── frontend/                        # ⚛️ Frontend (React + Vite + Tailwind)
│   ├── src/
│   └── package.json
│
├── alembic/                         # 🗃️ Database migrations
│   ├── env.py                       # OAuth-aware, auto-resolves credentials
│   └── versions/
│
├── scripts/                         # 🛠️ Operational scripts
│   ├── helpers.py                   # Shared connection / auth utilities
│   ├── manage_roles.py              # Postgres roles & Data API grants
│   ├── manage_branches.py           # Create / delete / reset branches
│   └── db_access.json               # Database-layer user lists (readwrite/readonly)
│
└── .github/workflows/               # ⚡ CI/CD pipelines
    ├── deploy-dev.yml               # Push to main → deploy to dev
    └── release-prod.yml             # Manual → deploy to prod + GitHub release
```

---

## ✅ Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.4+ | Python package management |
| [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install) | 0.287+ | Auth, bundle deploy |
| [Node.js](https://nodejs.org/) | 20+ | Frontend |

---

## 💻 Local Development

> **Prerequisite:** You need **CAN_MANAGE** permission on the Lakebase project to create branches and endpoints. An admin adds your email to `resources/lakebase.yml` permissions and deploys the bundle — see [👥 Developer onboarding](#-developer-onboarding).

### 1. Clone and install

```bash
git clone <repo-url> && cd lakebase-todo-app
uv sync --extra migrations --extra dev
cd frontend && npm install && cd ..
```

### 2. Authenticate

```bash
databricks auth login --host https://<workspace>.azuredatabricks.net --profile todo-app-dev
```

Create a `.env` file with just the profile name — everything else auto-detects:

```bash
DATABRICKS_CONFIG_PROFILE=todo-app-dev
```

### 3. Create your dev branch

```bash
uv run python scripts/manage_branches.py create dev-<your-name>
```

This forks from `production` and creates a read-write endpoint with 0.5–2 CU.

### 4. Run migrations

```bash
LAKEBASE_BRANCH_ID=dev-<your-name> uv run alembic upgrade head
```

### 5. Enable the Data API

In the Lakebase UI, navigate to your dev branch endpoint and click **Enable Data API**.

### 6. Start the app

```bash
# Backend (auto-detects your dev branch from your email)
uv run uvicorn app:app --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend && npm run dev
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173

### 🔍 How auto-detection works

The app reads `DATABRICKS_CONFIG_PROFILE` from `.env` and resolves everything else via the SDK:

| Setting | Auto-detected value |
|---|---|
| Branch | `dev-{username}` from your email (e.g. `dev-taylor-isbell`) |
| Endpoint | `primary` |
| Database | `databricks_postgres` (the default DB) |
| Data API URL | Constructed from endpoint host + workspace ID |
| User | Your Databricks email |
| Password | OAuth token (auto-refreshed) |

Service principals default to the `production` branch. Set `LAKEBASE_BRANCH_ID` explicitly to override.

---

## 🏗️ Infrastructure

Infrastructure is managed with **Databricks Asset Bundles** — the Lakebase project and platform ACLs are declared in `resources/lakebase.yml` and deployed alongside the app via `databricks bundle deploy`. The CI service principal becomes the project owner and gets `databricks_superuser`.

### 👥 Developer onboarding

To give a new developer access:

1. **Platform access** — Add their email to `resources/lakebase.yml` permissions with `CAN_MANAGE`
2. **Database access** — Add their email to `scripts/db_access.json` → `readwrite` list
3. Commit and push to main — the deploy pipeline handles everything (bundle deploy + role provisioning + migrations)
4. Have them follow the [💻 Local Development](#-local-development) steps above

### 🔐 Two permission layers

| Layer | Controls | Managed by |
|---|---|---|
| **Project ACLs** | Platform ops (create branches, manage endpoints) | `resources/lakebase.yml` |
| **Postgres roles** | Data access (SELECT, INSERT, etc.) + Data API | `scripts/manage_roles.py` + `scripts/db_access.json` |

These are independent — CAN_MANAGE does not grant database access, and vice versa. Both are provisioned automatically by the deploy pipeline.

---

## ⚡ CI/CD

All workflows authenticate via an **Azure Entra ID service principal** (`ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_TENANT_ID`). No PATs, no manual token rotation.

### 🟢 Deploy to Dev (`deploy-dev.yml`)

Triggers on every push to `main`:

1. `databricks bundle deploy -t dev` — creates/updates the App + Lakebase project + ACLs
2. `manage_roles.py --app` — creates Postgres roles for CI + App service principals
3. Provision user roles from `scripts/db_access.json` (readwrite + readonly)
4. `alembic upgrade head` — runs migrations on production branch
5. `databricks bundle run -t dev` — deploys app source code

### 🏷️ Release to Prod (`release-prod.yml`)

Manual trigger from `main` with a version number:

1. Runs tests (ruff + pytest)
2. Same deploy flow as dev but targeting `prod`
3. Creates a Git tag and GitHub Release

---

## 🗃️ Database Migrations

Alembic manages Postgres schema changes. The `alembic/env.py` resolves credentials via the Databricks SDK — no connection strings to manage.

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Target a specific branch
LAKEBASE_BRANCH_ID=dev-taylor-isbell uv run alembic upgrade head

# Generate a new migration from model changes
uv run alembic revision --autogenerate -m "add_audit_log_table"

# Show current version
uv run alembic current

# Downgrade one step
uv run alembic downgrade -1
```

---

## 🛠️ Scripts

### `manage_roles.py` — Postgres roles and permissions

```bash
# Developer roles (read-write)
uv run python scripts/manage_roles.py --engineers dev1@co.com dev2@co.com

# Read-only roles
uv run python scripts/manage_roles.py --readonly analyst@co.com

# CI/CD: create SERVICE_PRINCIPAL roles for the CI SP and App SP
uv run python scripts/manage_roles.py --app lakebase-todo-app-dev
```

Each role gets: CONNECT, USAGE, CRUD on all tables/sequences, ALTER DEFAULT PRIVILEGES for future objects, and a GRANT to the Data API `authenticator` role (if enabled).

### `manage_branches.py` — Lakebase branch lifecycle

```bash
uv run python scripts/manage_branches.py list
uv run python scripts/manage_branches.py create dev-alex
uv run python scripts/manage_branches.py create dev-alex --min-cu 0.5 --max-cu 4
uv run python scripts/manage_branches.py reset dev-alex
uv run python scripts/manage_branches.py delete dev-alex
```

---

## 🏛️ Architecture

```
┌─────────────────────────────────┐
│         Databricks App          │
│  ┌──────────┐  ┌─────────────┐  │
│  │  React   │  │   FastAPI   │  │
│  │ Frontend │──│   Backend   │  │
│  └──────────┘  └──────┬──────┘  │
└────────────────────────┼────────┘
                         │ Data API (PostgREST)
                         ▼
              ┌─────────────────────┐
              │  Lakebase Postgres  │
              │  ┌───────────────┐  │
              │  │  production   │  │  ← deployed app
              │  ├───────────────┤  │
              │  │  dev-taylor   │  │  ← local dev
              │  ├───────────────┤  │
              │  │  dev-alex     │  │  ← another developer
              │  └───────────────┘  │
              └─────────────────────┘
```

### 📡 Data API (PostgREST)

The backend uses the [Lakebase Data API](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/data-api) instead of direct Postgres connections. This is a PostgREST-compatible REST interface that auto-generates endpoints from your database schema.

- Must be **enabled per-endpoint** via the Lakebase UI
- Creates an `authenticator` Postgres role that assumes user identities
- Each user needs `GRANT "user@email" TO authenticator` (handled by `manage_roles.py`)
- The project owner **cannot** use the Data API (authenticator can't assume superuser roles)

### 🌿 Branching

Lakebase branches are **copy-on-write** — creating a branch is instant and doesn't duplicate data. Each developer gets an isolated branch forked from production.

Auto-detection convention:
- **Service principals** → `production` branch
- **Users** → `dev-{username}` branch (derived from email)

---

## 📚 References

- [Lakebase Data API](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/data-api)
- [Lakebase API guide](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/api-usage)
- [Grant user access tutorial](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/grant-user-access-tutorial)
- [Branch-based dev workflow](https://learn.microsoft.com/en-us/azure/databricks/oltp/projects/dev-workflow-tutorial)
- [Databricks Apps deployment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy)
- [Alembic documentation](https://alembic.sqlalchemy.org/)
