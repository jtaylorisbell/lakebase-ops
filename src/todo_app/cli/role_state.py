"""Live state queries and diff engine for declarative role management."""

from __future__ import annotations

from dataclasses import dataclass, field

from todo_app.cli.role_config import AccessLevel, DesiredState

# Roles that should never appear in diffs or be revoked.
SYSTEM_ROLES = frozenset(
    {
        "authenticator",
        "anon",
        "databricks_superuser",
        "pg_database_owner",
        "pg_read_all_data",
        "pg_write_all_data",
        "pg_monitor",
        "pg_read_all_settings",
        "pg_read_all_stats",
        "pg_stat_scan_tables",
        "pg_signal_backend",
        "pg_read_server_files",
        "pg_write_server_files",
        "pg_execute_server_program",
        "pg_checkpoint",
        "pg_maintain",
        "pg_use_reserved_connections",
        "pg_create_subscription",
    }
)

SYSTEM_ROLE_PREFIXES = ("pg_", "databricks_")


@dataclass
class LiveRole:
    name: str
    access: AccessLevel | None  # None = role exists but has no grants
    has_authenticator: bool


@dataclass
class RoleDiffEntry:
    role_name: str
    role_type: str  # "user" | "app"
    action: str  # "create" | "upgrade" | "downgrade" | "revoke" | "grant_authenticator"
    desired_access: AccessLevel | None
    current_access: AccessLevel | None
    needs_authenticator: bool


@dataclass
class RoleDiff:
    to_create: list[RoleDiffEntry] = field(default_factory=list)
    to_change: list[RoleDiffEntry] = field(default_factory=list)
    to_revoke: list[RoleDiffEntry] = field(default_factory=list)
    authenticator_grants: list[RoleDiffEntry] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.to_create or self.to_change or self.to_revoke or self.authenticator_grants)


def _is_system_role(name: str) -> bool:
    if name in SYSTEM_ROLES:
        return True
    return any(name.startswith(p) for p in SYSTEM_ROLE_PREFIXES)


def query_live_roles(cur) -> dict[str, LiveRole]:
    """Query Postgres for existing roles, their grants, and authenticator membership.

    Returns a dict of {role_name: LiveRole} excluding system roles.
    """
    # Get all non-system roles
    cur.execute(
        "SELECT rolname FROM pg_roles WHERE rolcanlogin = true OR rolname IN "
        "(SELECT grantee FROM information_schema.role_table_grants "
        " WHERE table_schema = 'public')"
    )
    all_roles = {row[0] for row in cur.fetchall()}

    # Determine access level: check for INSERT privilege → readwrite, SELECT only → readonly
    cur.execute(
        "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema = 'public'"
    )
    role_privileges: dict[str, set[str]] = {}
    for grantee, priv in cur.fetchall():
        role_privileges.setdefault(grantee, set()).add(priv)

    # Check authenticator membership
    cur.execute(
        "SELECT m.roleid, m.member, r.rolname AS member_name "
        "FROM pg_auth_members m "
        "JOIN pg_roles r ON m.member = r.oid "
        "WHERE m.roleid = (SELECT oid FROM pg_roles WHERE rolname = 'authenticator')"
    )
    authenticator_members = {row[2] for row in cur.fetchall()}

    result: dict[str, LiveRole] = {}
    for name in all_roles:
        if _is_system_role(name):
            continue

        privs = role_privileges.get(name, set())
        if "INSERT" in privs:
            access = AccessLevel.readwrite
        elif "SELECT" in privs:
            access = AccessLevel.readonly
        else:
            access = None

        result[name] = LiveRole(
            name=name,
            access=access,
            has_authenticator=name in authenticator_members,
        )

    return result


def compute_diff(desired: DesiredState, live: dict[str, LiveRole]) -> RoleDiff:
    """Compare desired state against live roles and return a diff."""
    diff = RoleDiff()

    # Build desired map: {role_name: (access, role_type)}
    desired_map: dict[str, tuple[AccessLevel, str]] = {}
    for user in desired.users:
        desired_map[user.email] = (user.access, "user")
    for app_role in desired.apps:
        desired_map[app_role.name] = (app_role.access, "app")

    # Check desired roles against live state
    for name, (access, role_type) in desired_map.items():
        live_role = live.get(name)

        if live_role is None:
            # Role doesn't exist at all
            diff.to_create.append(
                RoleDiffEntry(
                    role_name=name,
                    role_type=role_type,
                    action="create",
                    desired_access=access,
                    current_access=None,
                    needs_authenticator=True,
                )
            )
        else:
            # Role exists — check access level
            if live_role.access != access:
                action = "upgrade" if access == AccessLevel.readwrite else "downgrade"
                diff.to_change.append(
                    RoleDiffEntry(
                        role_name=name,
                        role_type=role_type,
                        action=action,
                        desired_access=access,
                        current_access=live_role.access,
                        needs_authenticator=not live_role.has_authenticator,
                    )
                )
            # Check authenticator grant even if access level matches
            elif not live_role.has_authenticator:
                diff.authenticator_grants.append(
                    RoleDiffEntry(
                        role_name=name,
                        role_type=role_type,
                        action="grant_authenticator",
                        desired_access=access,
                        current_access=live_role.access,
                        needs_authenticator=True,
                    )
                )

    # Check for roles to revoke (live but not desired)
    for name, live_role in live.items():
        if name not in desired_map:
            diff.to_revoke.append(
                RoleDiffEntry(
                    role_name=name,
                    role_type="user",  # can't tell from live state
                    action="revoke",
                    desired_access=None,
                    current_access=live_role.access,
                    needs_authenticator=False,
                )
            )

    return diff


def format_diff(diff: RoleDiff) -> str:
    """Format a RoleDiff as human-readable output."""
    if not diff.has_changes:
        return "No changes detected."

    lines: list[str] = []

    for entry in diff.to_create:
        lines.append(f"  + {entry.role_name} ({entry.role_type}): {entry.desired_access.value}")

    for entry in diff.to_change:
        current = entry.current_access.value if entry.current_access else "none"
        lines.append(
            f"  ~ {entry.role_name} ({entry.role_type}): "
            f"{current} -> {entry.desired_access.value}"
        )

    for entry in diff.authenticator_grants:
        lines.append(f"  ~ {entry.role_name} ({entry.role_type}): needs authenticator grant")

    for entry in diff.to_revoke:
        current = entry.current_access.value if entry.current_access else "none"
        lines.append(f"  - {entry.role_name}: {current} (not in config)")

    return "\n".join(lines)
