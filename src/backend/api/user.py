"""Identify the current user from Databricks Apps headers (with a local-dev fallback)."""

from dataclasses import dataclass
from functools import lru_cache

from fastapi import Request

from backend.config import _workspace_client


@dataclass
class CurrentUser:
    email: str | None
    name: str | None

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.email:
            return self.email.split("@")[0]
        return "Unknown"

    @property
    def is_authenticated(self) -> bool:
        return bool(self.email)


@lru_cache(maxsize=1)
def _local_identity() -> tuple[str | None, str | None]:
    try:
        me = _workspace_client().current_user.me()
        return me.user_name, me.display_name
    except Exception:
        return None, None


def get_current_user(request: Request) -> CurrentUser:
    email = request.headers.get("X-Forwarded-Email")
    name = request.headers.get("X-Forwarded-Preferred-Username")
    if not email:
        email, fallback_name = _local_identity()
        name = name or fallback_name
    return CurrentUser(email=email, name=name)
