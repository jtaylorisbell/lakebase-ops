ifneq (,$(wildcard .env))
    include .env
    export
endif

PROJECT ?= todo-app-v2
BRANCH ?= production
EMAIL ?= $(shell git config user.email)
ROLE_ID ?= $(shell echo "$(EMAIL)" | sed 's/@.*//' | tr '.' '-')

# ── Bundle ──────────────────────────────────────────
.PHONY: deploy validate
validate:
	databricks bundle validate

deploy: validate
	databricks bundle deploy

# ── Migrations ──────────────────────────────────────
.PHONY: migrate migrate-status migrate-downgrade migrate-new
migrate:
	uv run alembic upgrade head

migrate-status:
	uv run alembic current

migrate-downgrade:
	uv run alembic downgrade -1

migrate-new:
	@read -p "Migration message: " msg; \
	uv run alembic revision -m "$$msg"

# ── Branches ────────────────────────────────────────
# Branch lifecycle wraps `databricks postgres` directly.
.PHONY: branch-list branch-create branch-reset branch-delete role-create
branch-list:
	databricks postgres list-branches projects/$(PROJECT)

branch-create:
	databricks postgres create-branch projects/$(PROJECT) \
		--role-id $(NAME) \
		--json '{"spec": {"source_branch": "projects/$(PROJECT)/branches/production", "no_expiry": true}}'
	databricks postgres create-endpoint projects/$(PROJECT)/branches/$(NAME) \
		--role-id primary \
		--json '{"spec": {"endpoint_type": "ENDPOINT_TYPE_READ_WRITE", "autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 2.0, "suspend_timeout_duration": "600s"}}'
	$(MAKE) role-create BRANCH=$(NAME)

branch-reset:
	databricks api post /api/2.0/postgres/projects/$(PROJECT)/branches/$(NAME):reset --json '{}'

branch-delete:
	databricks postgres delete-branch projects/$(PROJECT)/branches/$(NAME)

# Provision the calling user's OAuth Postgres role on a branch (defaults to your
# dev branch). EMAIL/ROLE_ID auto-derive from `git config user.email`.
role-create:
	databricks postgres create-role projects/$(PROJECT)/branches/$(BRANCH) \
		--role-id $(ROLE_ID) \
		--json '{"spec": {"identity_type": "USER", "postgres_role": "$(EMAIL)"}}'
