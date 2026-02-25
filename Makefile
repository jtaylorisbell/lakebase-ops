# lakebase-ops Makefile
# Load .env if it exists
ifneq (,$(wildcard .env))
    include .env
    export
endif

BRANCH ?= production

# ── Terraform ────────────────────────────────────
.PHONY: tf-init tf-plan tf-apply tf-destroy

tf-init:
	cd terraform && terraform init

tf-plan: tf-init
	cd terraform && terraform plan

tf-apply: tf-init
	cd terraform && terraform apply -auto-approve

tf-destroy:
	cd terraform && terraform destroy -auto-approve

# ── Databricks Asset Bundles (App) ───────────────
.PHONY: dab-validate dab-deploy

dab-validate:
	databricks bundle validate

dab-deploy: dab-validate
	databricks bundle deploy

# ── Roles ────────────────────────────────────────
.PHONY: roles roles-app

roles:
	cd scripts && uv run python manage_roles.py --from-env

roles-app:
	uv run python scripts/manage_roles.py --app $(APP_NAME)

# ── Migrations ───────────────────────────────────
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

# ── Branches ─────────────────────────────────────
.PHONY: branch-list branch-create branch-reset branch-delete

branch-list:
	cd scripts && uv run python manage_branches.py list

branch-create:
	cd scripts && uv run python manage_branches.py create $(NAME)

branch-reset:
	cd scripts && uv run python manage_branches.py reset $(NAME)

branch-delete:
	cd scripts && uv run python manage_branches.py delete $(NAME)
