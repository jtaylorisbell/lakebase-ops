"""enable Lakebase CDF: REPLICA IDENTITY FULL + companion function

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-05

Lakebase CDF needs `REPLICA IDENTITY FULL` on every captured table so the
write-ahead log records the full pre- and post-row state. Without it,
updates and deletes are silently dropped from the feed.

This migration:
  1. Sets REPLICA IDENTITY FULL on every table the App SP owns (uses
     `pg_class.relreplident <> 'f'` so re-running is a no-op).
  2. Defines `"{SCHEMA}".set_full_replica_identity()` — the function that
     a CREATE TABLE event trigger calls. The App SP can create functions
     in its own schema, so this is fine to do here.

Registering the actual event trigger is a separate, database-level step
that requires superuser. See `scripts/install_cdf_event_trigger.py` and
`make install-cdf-trigger` — those run as the deploying identity (project
owner / `databricks_superuser`), not the App SP.

Configure CDF in the Lakebase UI (Branch overview → Change Data Feed →
Start) after this migration plus the event-trigger install. See README
and AGENTS.md.
"""

from collections.abc import Sequence

from alembic import op
from backend.config import SCHEMA

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent ALTER for every existing table the App SP owns.
    op.execute(f"""
        DO $body$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT n.nspname AS schema_name, c.relname AS table_name
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = '{SCHEMA}'
                  AND c.relkind = 'r'
                  AND c.relreplident <> 'f'
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I.%I REPLICA IDENTITY FULL;',
                    r.schema_name, r.table_name
                );
            END LOOP;
        END $body$;
    """)

    # Event-trigger function in the app's owned schema.
    op.execute(f"""
        CREATE OR REPLACE FUNCTION "{SCHEMA}".set_full_replica_identity()
        RETURNS event_trigger
        LANGUAGE plpgsql
        AS $body$
        DECLARE obj record;
        BEGIN
            FOR obj IN
                SELECT * FROM pg_event_trigger_ddl_commands()
                WHERE command_tag = 'CREATE TABLE'
            LOOP
                EXECUTE format(
                    'ALTER TABLE %s REPLICA IDENTITY FULL;',
                    obj.object_identity
                );
            END LOOP;
        END $body$;
    """)

    # The event trigger that calls this function is installed separately
    # at deploy time by `make install-cdf-trigger` (runs as project owner
    # with databricks_superuser). See scripts/install_cdf_event_trigger.py.


def downgrade() -> None:
    op.execute(f'DROP FUNCTION IF EXISTS "{SCHEMA}".set_full_replica_identity()')
    op.execute(f"""
        DO $body$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT n.nspname AS schema_name, c.relname AS table_name
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = '{SCHEMA}'
                  AND c.relkind = 'r'
                  AND c.relreplident = 'f'
            LOOP
                EXECUTE format(
                    'ALTER TABLE %I.%I REPLICA IDENTITY DEFAULT;',
                    r.schema_name, r.table_name
                );
            END LOOP;
        END $body$;
    """)
