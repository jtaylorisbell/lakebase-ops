"""Shared utilities for Lakebase operational scripts.

Uses the Databricks SDK for OAuth authentication and credential resolution.
Falls back to PGHOST/PGUSER/PGPASSWORD environment variables when set.
"""

import os

import psycopg2
from dotenv import load_dotenv
from databricks.sdk import WorkspaceClient

load_dotenv()

_workspace_client = None


def get_workspace_client() -> WorkspaceClient:
    """Return an authenticated WorkspaceClient (cached).

    Uses the standard Databricks SDK unified auth — picks up
    DATABRICKS_HOST + cached OAuth from ``databricks auth login``.
    """
    global _workspace_client
    if _workspace_client is None:
        _workspace_client = WorkspaceClient()
    return _workspace_client


def resolve_host(
    project_id: str,
    branch_id: str,
    endpoint_id: str = "primary",
) -> str:
    """Resolve the Postgres host from a Lakebase endpoint.

    Falls back to PGHOST environment variable if set.
    """
    if os.getenv("PGHOST"):
        return os.environ["PGHOST"]

    w = get_workspace_client()
    endpoint_name = (
        f"projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}"
    )
    try:
        endpoint = w.postgres.get_endpoint(name=endpoint_name)
        return endpoint.status.hosts.host
    except Exception:
        # Fallback: list endpoints on the branch and use the first one
        parent = f"projects/{project_id}/branches/{branch_id}"
        for ep in w.postgres.list_endpoints(parent=parent):
            return ep.status.hosts.host
        raise


def resolve_user() -> str:
    """Resolve the Postgres username.

    Falls back to PGUSER environment variable if set.
    For service principals, uses the client_id.
    For users, uses the email address.
    """
    if os.getenv("PGUSER"):
        return os.environ["PGUSER"]

    w = get_workspace_client()
    # Azure SP auth: config.client_id is None, use azure_client_id
    if w.config.client_id or w.config.azure_client_id:
        return w.config.client_id or w.config.azure_client_id

    me = w.current_user.me()
    return me.user_name


def resolve_password(
    project_id: str,
    branch_id: str,
    endpoint_id: str = "primary",
) -> str:
    """Resolve the Postgres password via OAuth token generation.

    Falls back to PGPASSWORD environment variable if set.
    """
    if os.getenv("PGPASSWORD"):
        return os.environ["PGPASSWORD"]

    w = get_workspace_client()
    endpoint_name = (
        f"projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}"
    )

    # Try configured endpoint, fall back to discovering the actual one
    try:
        w.postgres.get_endpoint(name=endpoint_name)
    except Exception:
        parent = f"projects/{project_id}/branches/{branch_id}"
        for ep in w.postgres.list_endpoints(parent=parent):
            endpoint_name = ep.name
            break

    cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
    return cred.token


def get_pg_connection(
    host: str | None = None,
    database: str | None = None,
    project_id: str | None = None,
    branch_id: str | None = None,
    endpoint_id: str = "primary",
):
    """Open a psycopg2 connection to a Lakebase Postgres branch.

    Connection parameters are resolved via the Databricks SDK when not
    explicitly provided or set via environment variables.

    Parameters
    ----------
    host : str, optional
        Override the resolved host.
    database : str, optional
        Override PGDATABASE (default: databricks_postgres).
    project_id : str, optional
        Lakebase project ID (falls back to LAKEBASE_PROJECT_ID or 'my-app').
    branch_id : str, optional
        Lakebase branch ID (falls back to LAKEBASE_BRANCH_ID or 'production').
    endpoint_id : str
        Endpoint ID (default: primary).
    """
    _project = project_id or os.getenv("LAKEBASE_PROJECT_ID", "todo-app")
    _branch = branch_id or os.getenv("LAKEBASE_BRANCH_ID", "production")

    return psycopg2.connect(
        host=host or resolve_host(_project, _branch, endpoint_id),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=database or os.getenv("PGDATABASE", "databricks_postgres"),
        user=resolve_user(),
        password=resolve_password(_project, _branch, endpoint_id),
        sslmode="require",
    )
