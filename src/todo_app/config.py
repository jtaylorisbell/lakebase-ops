"""Configuration management for Todo App."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger()


def _get_workspace_client():
    """Return a cached WorkspaceClient instance."""
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


class OAuthTokenManager:
    """Manages OAuth tokens for Lakebase with automatic refresh."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: datetime | None = None
        self._endpoint_name: str | None = None

    def get_token(self, endpoint_name: str) -> str | None:
        if not endpoint_name:
            return None

        if (
            self._token
            and self._endpoint_name == endpoint_name
            and self._expires_at
            and datetime.now() < self._expires_at - timedelta(minutes=5)
        ):
            return self._token

        try:
            logger.info("generating_oauth_token", endpoint=endpoint_name)
            w = _get_workspace_client()
            cred = w.postgres.generate_database_credential(endpoint=endpoint_name)

            self._token = cred.token
            self._endpoint_name = endpoint_name
            self._expires_at = datetime.now() + timedelta(minutes=55)
            return self._token
        except Exception as e:
            logger.error("oauth_token_generation_failed", error=str(e))
            return None


_token_manager = OAuthTokenManager()
_resolved_endpoints: dict[str, str] = {}


class LakebaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LAKEBASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database: str = "databricks_postgres"
    user: str = ""
    password: str = ""
    project_id: str = "todo-app"
    branch_id: str = ""
    endpoint_id: str = "primary"
    data_api_url: str = ""

    def get_branch_id(self) -> str:
        """Get the branch ID, auto-detecting from Databricks identity if not set.

        Convention:
        - Explicit branch_id env var: use it
        - Service principal: "production"
        - User: "dev-{username}" derived from email
        """
        if self.branch_id:
            return self.branch_id

        w = _get_workspace_client()
        if w.config.client_id or w.config.azure_client_id:
            return "production"

        me = w.current_user.me()
        username = me.user_name.split("@")[0].replace(".", "-").lower()
        return f"dev-{username}"

    @property
    def endpoint_name(self) -> str:
        branch = self.get_branch_id()
        return f"projects/{self.project_id}/branches/{branch}/endpoints/{self.endpoint_id}"

    def get_endpoint_name(self) -> str:
        """Resolve the actual endpoint name, discovering it if the configured ID doesn't exist.

        The default production branch may have an auto-provisioned endpoint with
        a different ID than 'default'. This method tries the configured name first,
        then falls back to listing endpoints on the branch.
        """
        from databricks.sdk.errors import NotFound

        expected = self.endpoint_name
        if expected in _resolved_endpoints:
            return _resolved_endpoints[expected]

        w = _get_workspace_client()
        try:
            w.postgres.get_endpoint(name=expected)
            _resolved_endpoints[expected] = expected
            return expected
        except NotFound:
            parent = f"projects/{self.project_id}/branches/{self.get_branch_id()}"
            for ep in w.postgres.list_endpoints(parent=parent):
                _resolved_endpoints[expected] = ep.name
                return ep.name
            raise

    def get_data_api_url(self) -> str:
        """Get the Data API URL, constructing from workspace host + endpoint if not set."""
        if self.data_api_url:
            return self.data_api_url.rstrip("/")

        w = _get_workspace_client()
        host = w.config.host.rstrip("/")
        endpoint_name = self.get_endpoint_name()
        return f"{host}/api/2.0/lakebase/{endpoint_name}/data"

    def get_host(self) -> str:
        """Resolve the Postgres host dynamically from the Lakebase endpoint."""
        w = _get_workspace_client()
        endpoint = w.postgres.get_endpoint(name=self.get_endpoint_name())
        return endpoint.status.hosts.host

    def get_user(self) -> str:
        """Get the Postgres user, auto-detecting from Databricks identity if not set.

        The Postgres role name must match the identity:
        - Service principal: client_id (e.g. '64cabdb0-...')
        - User: email (e.g. 'user@company.com')
        """
        if self.user:
            return self.user

        w = _get_workspace_client()
        if w.config.client_id or w.config.azure_client_id:
            return w.config.client_id or w.config.azure_client_id

        me = w.current_user.me()
        return me.user_name

    def get_password(self) -> str:
        """Get the database password, generating an OAuth token if needed."""
        if self.password:
            return self.password

        token = _token_manager.get_token(endpoint_name=self.get_endpoint_name())
        return token or self.password


class UserSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="USER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    email: str = ""
    name: str = ""

    def _get_me(self):
        """Fetch the current Databricks user identity."""
        return _get_workspace_client().current_user.me()

    def get_email(self) -> str:
        """Get user email, auto-detecting from Databricks identity if not set."""
        if self.email:
            return self.email
        try:
            return self._get_me().user_name
        except Exception:
            return self.email

    def get_name(self) -> str:
        """Get user display name, auto-detecting from Databricks identity if not set."""
        if self.name:
            return self.name
        try:
            return self._get_me().display_name or ""
        except Exception:
            return self.name


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"

    @property
    def lakebase(self) -> LakebaseSettings:
        return LakebaseSettings()

    @property
    def user(self) -> UserSettings:
        return UserSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
