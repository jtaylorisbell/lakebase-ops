"""Create Postgres roles and grant database permissions."""

import json
from pathlib import Path
from typing import Annotated

import typer

from todo_app.cli.role_config import AccessLevel, load_config
from todo_app.cli.role_state import compute_diff, format_diff, query_live_roles
from todo_app.helpers import get_pg_connection, get_workspace_client

app = typer.Typer(help="Manage Lakebase Postgres roles.")

# ── SQL templates ────────────────────────────────

SQL_CREATE_ROLE = "SELECT databricks_create_role(%s, 'USER')"
SQL_CREATE_SP_ROLE = "SELECT databricks_create_role(%s, 'SERVICE_PRINCIPAL')"

SQL_GRANT_READWRITE = """
-- Connect + schema access
GRANT CONNECT ON DATABASE databricks_postgres TO {role};
GRANT USAGE  ON SCHEMA public TO {role};
GRANT CREATE ON SCHEMA public TO {role};

-- Existing objects
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES    IN SCHEMA public TO {role};
GRANT USAGE, SELECT                  ON ALL SEQUENCES IN SCHEMA public TO {role};

-- Future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES    TO {role};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT                  ON SEQUENCES TO {role};
"""

SQL_GRANT_READONLY = """
GRANT CONNECT ON DATABASE databricks_postgres TO {role};
GRANT USAGE   ON SCHEMA public TO {role};

GRANT SELECT ON ALL TABLES    IN SCHEMA public TO {role};
GRANT USAGE  ON ALL SEQUENCES IN SCHEMA public TO {role};

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES    TO {role};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE  ON SEQUENCES TO {role};
"""

SQL_REVOKE_WRITE = """
REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM {role};
REVOKE CREATE ON SCHEMA public FROM {role};

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE INSERT, UPDATE, DELETE ON TABLES FROM {role};
"""

SQL_GRANT_TO_AUTHENTICATOR = "GRANT {role} TO authenticator"


def _quote_role(email: str) -> str:
    """Postgres-quote a role name (email addresses need double-quoting)."""
    return f'"{email}"'


def ensure_role(cur, email: str) -> None:
    """Create the OAuth Postgres role if it doesn't already exist."""
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (email,))
    if cur.fetchone():
        print(f"  + Role already exists: {email}")
        return
    cur.execute(SQL_CREATE_ROLE, (email,))
    print(f"  + Created role: {email}")


def ensure_sp_role(cur, identity: str) -> None:
    """Create a SERVICE_PRINCIPAL Postgres role if it doesn't already exist."""
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (identity,))
    if cur.fetchone():
        print(f"  + SP role already exists: {identity}")
        return
    cur.execute(SQL_CREATE_SP_ROLE, (identity,))
    print(f"  + Created SP role: {identity}")


def grant_permissions(cur, email: str, readonly: bool = False) -> None:
    """Grant Postgres permissions to a role."""
    import psycopg2

    role = _quote_role(email)
    template = SQL_GRANT_READONLY if readonly else SQL_GRANT_READWRITE
    cur.execute(template.format(role=role))
    mode = "read-only" if readonly else "read-write"
    print(f"  + Granted {mode} on public schema to {email}")

    try:
        cur.execute(SQL_GRANT_TO_AUTHENTICATOR.format(role=role))
        print(f"  + Granted Data API access to {email}")
    except (psycopg2.errors.UndefinedObject, psycopg2.errors.InsufficientPrivilege) as e:
        if "authenticator" in str(e) and "UndefinedObject" in type(e).__name__:
            print("  ! Data API not enabled — skipping authenticator grant")
        else:
            print("  ! Authenticator grant requires superuser — run via CI")


def _resolve_app_sp_id(app_name: str) -> str | None:
    """Look up the service principal client_id for a Databricks App."""
    w = get_workspace_client()
    app_obj = w.apps.get(name=app_name)
    sp_id = app_obj.service_principal_client_id
    if sp_id:
        print(f"App service principal ({app_name}): {sp_id}")
    else:
        print(f"Warning: App '{app_name}' has no service_principal_client_id")
    return sp_id


# ── provision (unchanged) ────────────────────────


@app.command()
def provision(
    app_name: Annotated[
        str | None, typer.Option("--app", help="Databricks App name (creates SP role).")
    ] = None,
    db_access: Annotated[
        Path | None,
        typer.Option(help="Path to JSON file with 'readwrite' and 'readonly' email lists."),
    ] = None,
    engineers: Annotated[
        list[str] | None, typer.Option(help="Emails for read-write access.")
    ] = None,
    readonly: Annotated[
        list[str] | None, typer.Option(help="Emails for read-only access.")
    ] = None,
) -> None:
    """Provision Postgres roles and grant database permissions."""
    # ── Collect emails from all sources ──────────
    readwrite = list(engineers or [])
    readonly_list = list(readonly or [])

    if db_access:
        with open(db_access) as f:
            data = json.load(f)
        readwrite += data.get("readwrite", [])
        readonly_list += data.get("readonly", [])

    readwrite = list(set(readwrite))
    readonly_list = list(set(readonly_list))

    # ── Resolve App SP identity (if --app) ───────
    app_sp_id = None
    if app_name:
        app_sp_id = _resolve_app_sp_id(app_name)

    if not app_sp_id and not readwrite and not readonly_list:
        print("No roles to provision. Pass --app, --db-access, --engineers, or --readonly.")
        raise typer.Exit(code=1)

    # ── Single connection for all operations ─────
    conn = get_pg_connection()
    conn.autocommit = True

    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")

            if app_sp_id:
                print(f"\nProvisioning App SP: {app_sp_id}")
                ensure_sp_role(cur, app_sp_id)
                grant_permissions(cur, app_sp_id)

            for email in readwrite:
                print(f"\nProvisioning (read-write): {email}")
                ensure_role(cur, email)
                grant_permissions(cur, email)

            for email in readonly_list:
                print(f"\nProvisioning (read-only): {email}")
                ensure_role(cur, email)
                grant_permissions(cur, email, readonly=True)
    finally:
        conn.close()

    print("\nDone.")


# ── diff ─────────────────────────────────────────


@app.command()
def diff(
    config: Annotated[
        Path, typer.Option(help="Path to roles YAML config.")
    ] = Path("scripts/roles.yml"),
    app_name: Annotated[
        str | None, typer.Option("--app", help="Databricks App name (includes its SP).")
    ] = None,
) -> None:
    """Show differences between desired config and live Postgres roles."""
    from todo_app.cli.role_config import AppRole

    desired = load_config(config)

    if app_name:
        sp_id = _resolve_app_sp_id(app_name)
        if sp_id:
            desired.apps.append(AppRole(name=sp_id, access=AccessLevel.readwrite))

    conn = get_pg_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            live = query_live_roles(cur)
    finally:
        conn.close()

    role_diff = compute_diff(desired, live)

    if not role_diff.has_changes:
        print("No changes detected.")
        raise typer.Exit(code=0)

    print("Changes detected:\n")
    print(format_diff(role_diff))
    raise typer.Exit(code=1)


# ── sync ─────────────────────────────────────────


@app.command()
def sync(
    config: Annotated[
        Path, typer.Option(help="Path to roles YAML config.")
    ] = Path("scripts/roles.yml"),
    app_name: Annotated[
        str | None, typer.Option("--app", help="Databricks App name (includes its SP).")
    ] = None,
    revoke: Annotated[
        bool, typer.Option("--revoke", help="Revoke roles not in config.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show diff without applying changes.")
    ] = False,
) -> None:
    """Sync live Postgres roles to match the desired config."""
    import psycopg2

    from todo_app.cli.role_config import AppRole

    desired = load_config(config)

    if app_name:
        sp_id = _resolve_app_sp_id(app_name)
        if sp_id:
            desired.apps.append(AppRole(name=sp_id, access=AccessLevel.readwrite))

    conn = get_pg_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            live = query_live_roles(cur)
            role_diff = compute_diff(desired, live)

            if not role_diff.has_changes:
                print("No changes detected.")
                return

            print("Changes detected:\n")
            print(format_diff(role_diff))

            if dry_run:
                print("\nDry run — no changes applied.")
                return

            print("\nApplying changes...\n")
            cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")

            # Create new roles
            for entry in role_diff.to_create:
                role = _quote_role(entry.role_name)
                if entry.role_type == "app":
                    ensure_sp_role(cur, entry.role_name)
                else:
                    ensure_role(cur, entry.role_name)

                template = (
                    SQL_GRANT_READONLY
                    if entry.desired_access == AccessLevel.readonly
                    else SQL_GRANT_READWRITE
                )
                cur.execute(template.format(role=role))
                print(f"  + Granted {entry.desired_access.value} to {entry.role_name}")

                try:
                    cur.execute(SQL_GRANT_TO_AUTHENTICATOR.format(role=role))
                    print(f"  + Granted Data API access to {entry.role_name}")
                except (
                    psycopg2.errors.UndefinedObject,
                    psycopg2.errors.InsufficientPrivilege,
                ):
                    print("  ! Authenticator grant skipped")

            # Change access level (upgrade/downgrade)
            for entry in role_diff.to_change:
                role = _quote_role(entry.role_name)

                if entry.action == "downgrade":
                    cur.execute(SQL_REVOKE_WRITE.format(role=role))
                    cur.execute(SQL_GRANT_READONLY.format(role=role))
                    print(f"  ~ Downgraded {entry.role_name} to readonly")
                else:
                    cur.execute(SQL_GRANT_READWRITE.format(role=role))
                    print(f"  ~ Upgraded {entry.role_name} to readwrite")

                if entry.needs_authenticator:
                    try:
                        cur.execute(SQL_GRANT_TO_AUTHENTICATOR.format(role=role))
                        print(f"  + Granted Data API access to {entry.role_name}")
                    except (
                        psycopg2.errors.UndefinedObject,
                        psycopg2.errors.InsufficientPrivilege,
                    ):
                        print("  ! Authenticator grant skipped")

            # Fix missing authenticator grants
            for entry in role_diff.authenticator_grants:
                role = _quote_role(entry.role_name)
                try:
                    cur.execute(SQL_GRANT_TO_AUTHENTICATOR.format(role=role))
                    print(f"  + Granted Data API access to {entry.role_name}")
                except (
                    psycopg2.errors.UndefinedObject,
                    psycopg2.errors.InsufficientPrivilege,
                ):
                    print("  ! Authenticator grant skipped")

            # Revoke roles not in config (only with --revoke)
            if revoke and role_diff.to_revoke:
                for entry in role_diff.to_revoke:
                    role = _quote_role(entry.role_name)
                    cur.execute(SQL_REVOKE_WRITE.format(role=role))
                    cur.execute(
                        f"REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM {role};"
                        f"REVOKE USAGE ON ALL SEQUENCES IN SCHEMA public FROM {role};"
                        f"REVOKE USAGE ON SCHEMA public FROM {role};"
                        f"REVOKE CONNECT ON DATABASE databricks_postgres FROM {role};"
                    )
                    print(f"  - Revoked all grants from {entry.role_name}")
            elif role_diff.to_revoke:
                print(
                    f"\n{len(role_diff.to_revoke)} role(s) not in config "
                    "(pass --revoke to remove them)."
                )

    finally:
        conn.close()

    print("\nDone.")
