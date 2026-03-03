"""YAML config parser and data model for declarative role management."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml


class AccessLevel(StrEnum):
    readwrite = "readwrite"
    readonly = "readonly"


@dataclass
class UserRole:
    email: str
    access: AccessLevel


@dataclass
class AppRole:
    name: str
    access: AccessLevel


@dataclass
class DesiredState:
    users: list[UserRole] = field(default_factory=list)
    apps: list[AppRole] = field(default_factory=list)


def load_config(path: Path) -> DesiredState:
    """Parse a roles YAML file into a DesiredState.

    Raises ValueError on duplicate emails.
    """
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    users: list[UserRole] = []
    seen_emails: set[str] = set()

    for entry in data.get("users", []):
        email = entry["email"]
        if email in seen_emails:
            raise ValueError(f"Duplicate email in config: {email}")
        seen_emails.add(email)
        users.append(UserRole(email=email, access=AccessLevel(entry["access"])))

    return DesiredState(users=users)
