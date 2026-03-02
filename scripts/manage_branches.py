#!/usr/bin/env python3
"""Manage Lakebase branches via the Databricks SDK.

Actions:
    list     — List all branches in the project
    create   — Create a new child branch (from production by default)
    delete   — Delete a branch
    reset    — Reset a branch from its parent (pull latest data)

Usage:
    uv run python manage_branches.py list
    uv run python manage_branches.py create dev/alex
    uv run python manage_branches.py create dev/alex --parent development
    uv run python manage_branches.py create dev/alex --min-cu 0.5 --max-cu 2
    uv run python manage_branches.py reset  dev/alex
    uv run python manage_branches.py delete dev/alex
"""

import argparse
import os

from databricks.sdk.service.postgres import (
    Branch,
    BranchSpec,
    Endpoint,
    EndpointSpec,
    EndpointType,
)

from helpers import get_workspace_client


PROJECT_ID = os.getenv("LAKEBASE_PROJECT_ID", "todo-app")


def list_branches(w, project_id: str) -> None:
    """Print all branches in the project."""
    parent = f"projects/{project_id}"
    branches = list(w.postgres.list_branches(parent=parent))

    if not branches:
        print("No branches found.")
        return

    print(f"{'Branch':<40} {'Parent':<40}")
    print("-" * 80)
    for b in branches:
        name = b.name or ""
        parent_name = b.spec.parent if b.spec else "-"
        # Extract just the branch ID from the full resource name
        branch_id = name.split("/branches/")[-1] if "/branches/" in name else name
        parent_id = (
            parent_name.split("/branches/")[-1]
            if parent_name and "/branches/" in parent_name
            else (parent_name or "-")
        )
        print(f"{branch_id:<40} {parent_id:<40}")


def create_branch(
    w,
    project_id: str,
    branch_id: str,
    parent_branch: str = "production",
    min_cu: float = 0.5,
    max_cu: float = 2.0,
) -> None:
    """Create a child branch with a read-write endpoint."""
    parent = f"projects/{project_id}"
    print(f"Creating branch '{branch_id}' from '{parent_branch}'...")

    # Create the branch
    op = w.postgres.create_branch(
        parent=parent,
        branch=Branch(
            spec=BranchSpec(
                source_branch=f"{parent}/branches/{parent_branch}",
                no_expiry=True,
            ),
        ),
        branch_id=branch_id,
    )
    branch = op.wait()
    print(f"  Branch created: {branch.name}")

    # Create a read-write endpoint on the new branch
    branch_parent = f"{parent}/branches/{branch_id}"
    ep_op = w.postgres.create_endpoint(
        parent=branch_parent,
        endpoint=Endpoint(
            spec=EndpointSpec(
                endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
                autoscaling_limit_min_cu=min_cu,
                autoscaling_limit_max_cu=max_cu,
                suspend_timeout_duration=600,
            ),
        ),
        endpoint_id="primary",
    )
    ep_op.wait()
    print(f"  Endpoint created with {min_cu}-{max_cu} CU")
    print("Done.")


def reset_branch(w, project_id: str, branch_id: str) -> None:
    """Reset a branch from its parent (re-syncs schema + data).

    Uses the raw API — reset is not yet in the typed SDK.
    """
    print(f"Resetting branch '{branch_id}' from its parent...")
    w.api_client.do(
        "POST",
        f"/api/2.0/postgres/projects/{project_id}/branches/{branch_id}:reset",
        body={},
    )
    print("  Branch reset complete.")


def delete_branch(w, project_id: str, branch_id: str) -> None:
    """Delete a branch and all its endpoints."""
    name = f"projects/{project_id}/branches/{branch_id}"
    print(f"Deleting branch '{branch_id}'...")
    w.postgres.delete_branch(name=name)
    print("  Branch deleted.")


def main():
    parser = argparse.ArgumentParser(description="Manage Lakebase branches.")
    sub = parser.add_subparsers(dest="action", required=True)

    # list
    sub.add_parser("list", help="List all branches.")

    # create
    p_create = sub.add_parser("create", help="Create a branch.")
    p_create.add_argument("branch_id", help="e.g. dev/alex")
    p_create.add_argument(
        "--parent", default="production", help="Parent branch ID."
    )
    p_create.add_argument("--min-cu", type=float, default=0.5)
    p_create.add_argument("--max-cu", type=float, default=2.0)

    # reset
    p_reset = sub.add_parser("reset", help="Reset branch from parent.")
    p_reset.add_argument("branch_id")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a branch.")
    p_delete.add_argument("branch_id")

    args = parser.parse_args()
    w = get_workspace_client()

    match args.action:
        case "list":
            list_branches(w, PROJECT_ID)
        case "create":
            create_branch(
                w, PROJECT_ID, args.branch_id,
                parent_branch=args.parent,
                min_cu=args.min_cu, max_cu=args.max_cu,
            )
        case "reset":
            reset_branch(w, PROJECT_ID, args.branch_id)
        case "delete":
            delete_branch(w, PROJECT_ID, args.branch_id)


if __name__ == "__main__":
    main()
