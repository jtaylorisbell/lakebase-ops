"""Configuration for the Todo App — auto-resolves Lakebase connection via Databricks SDK."""

from __future__ import annotations

import time
from functools import lru_cache
from urllib.parse import quote_plus

import structlog
from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

logger = structlog.get_logger()

SCHEMA = "todo_app"


@lru_cache
def _workspace_client() -> WorkspaceClient:
    return WorkspaceClient()


class _OAuthTokenManager:
    """Caches a Lakebase OAuth token and refreshes 5 minutes before expiry."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._endpoint: str | None = None

    def get(self, endpoint: str) -> str:
        if self._token and self._endpoint == endpoint and time.time() < self._expires_at:
            return self._token
        logger.info("generating_oauth_token", endpoint=endpoint)
        cred = _workspace_client().postgres.generate_database_credential(endpoint=endpoint)
        self._token = cred.token
        self._endpoint = endpoint
        self._expires_at = time.time() + 55 * 60
        return self._token


_token_manager = _OAuthTokenManager()


class LakebaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LAKEBASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_id: str = "todo-app"
    branch_id: str = ""
    endpoint_id: str = "primary"
    database: str = "databricks_postgres"

    def get_branch_id(self) -> str:
        """Resolve the branch — explicit env wins, then SP→production, user→dev-{username}."""
        if self.branch_id:
            return self.branch_id
        w = _workspace_client()
        if w.config.client_id or w.config.azure_client_id:
            return "production"
        username = w.current_user.me().user_name.split("@")[0].replace(".", "-").lower()
        return f"dev-{username}"

    def _endpoint_name(self) -> str:
        return (
            f"projects/{self.project_id}/branches/{self.get_branch_id()}"
            f"/endpoints/{self.endpoint_id}"
        )

    def get_host(self) -> str:
        endpoint = _workspace_client().postgres.get_endpoint(name=self._endpoint_name())
        return endpoint.status.hosts.host

    def get_user(self) -> str:
        w = _workspace_client()
        return w.config.client_id or w.config.azure_client_id or w.current_user.me().user_name

    def get_password(self) -> str:
        return _token_manager.get(self._endpoint_name())

    def get_database_url(self) -> str:
        return (
            f"postgresql+psycopg://{quote_plus(self.get_user())}:{quote_plus(self.get_password())}"
            f"@{self.get_host()}:5432/{self.database}"
            f"?sslmode=require&connect_timeout=30&options=-csearch_path%3D{SCHEMA}"
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = "INFO"

    @property
    def lakebase(self) -> LakebaseSettings:
        return LakebaseSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
