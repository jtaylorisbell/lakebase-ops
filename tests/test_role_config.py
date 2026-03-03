"""Unit tests for role config parsing and diff computation (no DB needed)."""

import textwrap
from pathlib import Path

import pytest

from todo_app.cli.role_config import AccessLevel, AppRole, DesiredState, UserRole, load_config
from todo_app.cli.role_state import LiveRole, RoleDiff, compute_diff, format_diff

# ── YAML parsing ─────────────────────────────────


def test_load_config_valid(tmp_path: Path):
    cfg = tmp_path / "roles.yml"
    cfg.write_text(
        textwrap.dedent("""\
        users:
          - email: alice@co.com
            access: readwrite
          - email: bob@co.com
            access: readonly
        """)
    )
    state = load_config(cfg)
    assert len(state.users) == 2
    assert state.users[0] == UserRole(email="alice@co.com", access=AccessLevel.readwrite)
    assert state.users[1] == UserRole(email="bob@co.com", access=AccessLevel.readonly)


def test_load_config_empty(tmp_path: Path):
    cfg = tmp_path / "roles.yml"
    cfg.write_text("")
    state = load_config(cfg)
    assert state.users == []
    assert state.apps == []


def test_load_config_no_users_key(tmp_path: Path):
    cfg = tmp_path / "roles.yml"
    cfg.write_text("other_key: value\n")
    state = load_config(cfg)
    assert state.users == []


def test_load_config_duplicate_email(tmp_path: Path):
    cfg = tmp_path / "roles.yml"
    cfg.write_text(
        textwrap.dedent("""\
        users:
          - email: alice@co.com
            access: readwrite
          - email: alice@co.com
            access: readonly
        """)
    )
    with pytest.raises(ValueError, match="Duplicate email"):
        load_config(cfg)


# ── Diff computation ─────────────────────────────


def test_diff_no_changes():
    desired = DesiredState(
        users=[UserRole(email="alice@co.com", access=AccessLevel.readwrite)]
    )
    live = {
        "alice@co.com": LiveRole(
            name="alice@co.com", access=AccessLevel.readwrite, has_authenticator=True
        )
    }
    diff = compute_diff(desired, live)
    assert not diff.has_changes


def test_diff_new_role():
    desired = DesiredState(
        users=[UserRole(email="alice@co.com", access=AccessLevel.readwrite)]
    )
    live: dict[str, LiveRole] = {}
    diff = compute_diff(desired, live)
    assert len(diff.to_create) == 1
    assert diff.to_create[0].role_name == "alice@co.com"
    assert diff.to_create[0].desired_access == AccessLevel.readwrite
    assert diff.to_create[0].action == "create"


def test_diff_upgrade():
    desired = DesiredState(
        users=[UserRole(email="alice@co.com", access=AccessLevel.readwrite)]
    )
    live = {
        "alice@co.com": LiveRole(
            name="alice@co.com", access=AccessLevel.readonly, has_authenticator=True
        )
    }
    diff = compute_diff(desired, live)
    assert len(diff.to_change) == 1
    assert diff.to_change[0].action == "upgrade"
    assert diff.to_change[0].desired_access == AccessLevel.readwrite
    assert diff.to_change[0].current_access == AccessLevel.readonly


def test_diff_downgrade():
    desired = DesiredState(
        users=[UserRole(email="alice@co.com", access=AccessLevel.readonly)]
    )
    live = {
        "alice@co.com": LiveRole(
            name="alice@co.com", access=AccessLevel.readwrite, has_authenticator=True
        )
    }
    diff = compute_diff(desired, live)
    assert len(diff.to_change) == 1
    assert diff.to_change[0].action == "downgrade"


def test_diff_revocation():
    desired = DesiredState(users=[])
    live = {
        "alice@co.com": LiveRole(
            name="alice@co.com", access=AccessLevel.readwrite, has_authenticator=True
        )
    }
    diff = compute_diff(desired, live)
    assert len(diff.to_revoke) == 1
    assert diff.to_revoke[0].role_name == "alice@co.com"
    assert diff.to_revoke[0].action == "revoke"


def test_diff_missing_authenticator():
    desired = DesiredState(
        users=[UserRole(email="alice@co.com", access=AccessLevel.readwrite)]
    )
    live = {
        "alice@co.com": LiveRole(
            name="alice@co.com", access=AccessLevel.readwrite, has_authenticator=False
        )
    }
    diff = compute_diff(desired, live)
    assert len(diff.authenticator_grants) == 1
    assert diff.authenticator_grants[0].action == "grant_authenticator"


def test_diff_app_role():
    desired = DesiredState(
        apps=[AppRole(name="sp-client-id-123", access=AccessLevel.readwrite)]
    )
    live: dict[str, LiveRole] = {}
    diff = compute_diff(desired, live)
    assert len(diff.to_create) == 1
    assert diff.to_create[0].role_type == "app"
    assert diff.to_create[0].role_name == "sp-client-id-123"


def test_diff_mixed():
    """New user + existing user (no change) + stale user → create + revoke."""
    desired = DesiredState(
        users=[
            UserRole(email="alice@co.com", access=AccessLevel.readwrite),
            UserRole(email="bob@co.com", access=AccessLevel.readonly),
        ]
    )
    live = {
        "bob@co.com": LiveRole(
            name="bob@co.com", access=AccessLevel.readonly, has_authenticator=True
        ),
        "charlie@co.com": LiveRole(
            name="charlie@co.com", access=AccessLevel.readwrite, has_authenticator=True
        ),
    }
    diff = compute_diff(desired, live)
    assert len(diff.to_create) == 1
    assert diff.to_create[0].role_name == "alice@co.com"
    assert len(diff.to_revoke) == 1
    assert diff.to_revoke[0].role_name == "charlie@co.com"
    assert len(diff.to_change) == 0


# ── format_diff ──────────────────────────────────


def test_format_diff_no_changes():
    diff = RoleDiff()
    assert format_diff(diff) == "No changes detected."


def test_format_diff_output():
    desired = DesiredState(
        users=[UserRole(email="new@co.com", access=AccessLevel.readwrite)]
    )
    live = {
        "old@co.com": LiveRole(
            name="old@co.com", access=AccessLevel.readonly, has_authenticator=True
        )
    }
    diff = compute_diff(desired, live)
    output = format_diff(diff)
    assert "+ new@co.com" in output
    assert "- old@co.com" in output
