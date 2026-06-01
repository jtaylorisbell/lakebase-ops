"""Alembic environment — resolves Lakebase OAuth credentials via Databricks SDK."""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool, text

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backend.config import SCHEMA, LakebaseSettings  # noqa: E402
from backend.db.schemas import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    settings = LakebaseSettings()
    engine = create_engine(settings.get_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=SCHEMA,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    raise RuntimeError("Offline migrations are not supported — credentials require live SDK auth.")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
