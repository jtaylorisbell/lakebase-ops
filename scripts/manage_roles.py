#!/usr/bin/env python3
"""Create Postgres roles and grant database permissions.

This script handles the *database-level* permission layer:
  - Creates OAuth roles for team members via databricks_create_role()
  - Grants appropriate Postgres privileges (CONNECT, USAGE, SELECT, etc.)

Roles are cluster-wide but table-level GRANTs are per-database. This script
grants on both the default ``databricks_postgres`` database (where the
databricks_auth extension lives) and the ``todoapp`` application database.

Usage:
    uv run python manage_roles.py --analysts analyst1@co.com analyst2@co.com
    uv run python manage_roles.py --engineers eng1@co.com eng2@co.com
    uv run python manage_roles.py --readonly reader@co.com
    uv run python manage_roles.py --from-env          # reads TEAM_* from .env
    uv run python manage_roles.py --app my-app-dev    # CI + App SP roles
"""

import argparse
import json
import os
import sys

from helpers import get_pg_connection, get_workspace_client


# ── Constants ───────────────────────────────────

APP_DATABASE = "todoapp"

# ── SQL templates ────────────────────────────────

SQL_CREATE_ROLE = "SELECT databricks_create_role(%s, 'USER')"
SQL_CREATE_SP_ROLE = "SELECT databricks_create_role(%s, 'SERVICE_PRINCIPAL')"

# Schema/table grants — run while connected to each target database.
# GRANT CONNECT references the current database via current_database().
SQL_GRANT_READWRITE = """
GRANT CONNECT ON DATABASE {database} TO {role};
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
GRANT CONNECT ON DATABASE {database} TO {role};
GRANT USAGE   ON SCHEMA public TO {role};

GRANT SELECT ON ALL TABLES    IN SCHEMA public TO {role};
GRANT USAGE  ON ALL SEQUENCES IN SCHEMA public TO {role};

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES    TO {role};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE  ON SEQUENCES TO {role};
"""


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


def grant_permissions(cur, email: str, database: str, readonly: bool = False) -> None:
    """Grant Postgres permissions to a role on the current database."""
    role = _quote_role(email)
    template = SQL_GRANT_READONLY if readonly else SQL_GRANT_READWRITE
    sql = template.format(role=role, database=database)
    cur.execute(sql)
    mode = "read-only" if readonly else "read-write"
    print(f"  + Granted {mode} on {database}.public to {email}")


def _grant_on_all_databases(
    identities: list[str],
    create_role_fn,
    readonly: bool = False,
) -> None:
    """Create roles and grant permissions on both default and app databases.

    1. Connects to databricks_postgres to create roles (extension lives here).
    2. Grants on databricks_postgres.
    3. Connects to the app database and grants there too (if it exists).
    """
    # Step 1: create roles + grant on databricks_postgres
    conn = get_pg_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")
            for identity in identities:
                print(f"\nProvisioning: {identity}")
                create_role_fn(cur, identity)
                grant_permissions(cur, identity, "databricks_postgres", readonly)
    finally:
        conn.close()

    # Step 2: grant on the app database (if it exists)
    try:
        app_conn = get_pg_connection(database=APP_DATABASE)
        app_conn.autocommit = True
        try:
            with app_conn.cursor() as cur:
                for identity in identities:
                    grant_permissions(cur, identity, APP_DATABASE, readonly)
        finally:
            app_conn.close()
    except Exception as e:
        # App database may not exist yet (e.g. first-time setup before migrations)
        print(f"\n  (Skipping {APP_DATABASE} grants — database may not exist: {e})")


def provision_app_roles(app_name: str) -> None:
    """Create Postgres roles for CI and App service principals.

    Detects the CI SP identity from the current SDK session and looks up
    the App SP client_id via the Databricks Apps API. Both get
    SERVICE_PRINCIPAL roles with read-write permissions.
    """
    w = get_workspace_client()

    identities: list[str] = []

    # CI service principal — the identity running this script
    me = w.current_user.me()
    print(f"\nCI service principal: {me.user_name}")
    identities.append(me.user_name)

    # App service principal — looked up via the Apps API
    app = w.apps.get(name=app_name)
    app_sp_id = app.service_principal_client_id
    if app_sp_id:
        print(f"App service principal ({app_name}): {app_sp_id}")
        identities.append(app_sp_id)
    else:
        print(f"Warning: App '{app_name}' has no service_principal_client_id")

    _grant_on_all_databases(identities, ensure_sp_role)
    print("\nDone.")


def provision_users(emails: list[str], readonly: bool = False) -> None:
    """Create roles and grant permissions for a list of users."""
    if not emails:
        return

    _grant_on_all_databases(emails, ensure_role, readonly)
    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Lakebase Postgres roles and permissions."
    )
    parser.add_argument(
        "--engineers",
        nargs="*",
        default=[],
        help="Emails for read-write access.",
    )
    parser.add_argument(
        "--analysts",
        nargs="*",
        default=[],
        help="Emails for read-write access (same as --engineers).",
    )
    parser.add_argument(
        "--readonly",
        nargs="*",
        default=[],
        help="Emails for read-only access.",
    )
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Read TEAM_ENGINEERS and TEAM_ANALYSTS from .env as JSON arrays.",
    )
    parser.add_argument(
        "--app",
        metavar="APP_NAME",
        help="Create SERVICE_PRINCIPAL roles for the CI SP and the Databricks App SP.",
    )
    args = parser.parse_args()

    # --app mode: create SP roles for CI + App service principals
    if args.app:
        provision_app_roles(args.app)
        return

    engineers = list(args.engineers)
    analysts = list(args.analysts)
    readonly = list(args.readonly)

    if args.from_env:
        engineers += json.loads(os.getenv("TEAM_ENGINEERS", "[]"))
        analysts += json.loads(os.getenv("TEAM_ANALYSTS", "[]"))

    readwrite = list(set(engineers + analysts))

    if not readwrite and not readonly:
        parser.print_help()
        sys.exit(1)

    provision_users(readwrite, readonly=False)
    provision_users(readonly, readonly=True)


if __name__ == "__main__":
    main()
