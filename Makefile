# lakebase-ops Makefile
# Load .env if it exists
ifneq (,$(wildcard .env))
    include .env
    export
endif

PROJECT ?= todo-app
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
.PHONY: roles-app roles-diff roles-sync

roles-app:
	uv run lbctl roles provision --app $(APP_NAME)

roles-diff:
	uv run lbctl roles diff --config scripts/roles.yml

roles-sync:
	uv run lbctl roles sync --config scripts/roles.yml

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

# ── Branches (databricks postgres CLI) ───────────
.PHONY: branch-list branch-create branch-reset branch-delete

branch-list:
	databricks postgres list-branches projects/$(PROJECT)

branch-create:
	databricks postgres create-branch projects/$(PROJECT) $(NAME) \
		--json '{"spec": {"source_branch": "projects/$(PROJECT)/branches/production", "no_expiry": true}}'
	databricks postgres create-endpoint projects/$(PROJECT)/branches/$(NAME) primary \
		--json '{"spec": {"endpoint_type": "ENDPOINT_TYPE_READ_WRITE", "autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 2.0, "suspend_timeout_duration": 600}}'

branch-reset:
	databricks api post /api/2.0/postgres/projects/$(PROJECT)/branches/$(NAME):reset --json '{}'

branch-delete:
	databricks postgres delete-branch projects/$(PROJECT)/branches/$(NAME)
