"""Alembic environment configuration.

Builds the database URL dynamically using LakebaseSettings and OAuthTokenManager
so that migrations work with Databricks OAuth — no hardcoded credentials.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from todo_app.config import LakebaseSettings  # noqa: E402
from todo_app.db.schemas import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _get_settings() -> LakebaseSettings:
    return LakebaseSettings()


def _build_url(lb: LakebaseSettings) -> str:
    """Build a SQLAlchemy database URL from LakebaseSettings + OAuth."""
    host = lb.get_host()
    user = lb.get_user()
    password = lb.get_password()
    return (
        f"postgresql+psycopg2://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:5432/{lb.database}"
        f"?sslmode=require"
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL to stdout."""
    lb = _get_settings()
    url = _build_url(lb)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the database."""
    lb = _get_settings()

    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _build_url(lb)

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
