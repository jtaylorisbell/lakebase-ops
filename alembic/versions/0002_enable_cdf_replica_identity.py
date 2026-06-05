"""enable Lakebase CDF: REPLICA IDENTITY FULL + auto-apply event trigger

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-05

Lakebase CDF needs `REPLICA IDENTITY FULL` on every captured table so the
write-ahead log records the full pre- and post-row state. Without it,
updates and deletes are silently dropped from the feed.

This migration:
  1. Sets REPLICA IDENTITY FULL on every table the App SP owns (uses
     `pg_class.relreplident <> 'f'` so re-running is a no-op).
  2. Defines a `set_full_replica_identity()` event-trigger function in the
     app schema.
  3. Tries to register the function as a global event trigger that fires
     after every CREATE TABLE. Creating an event trigger requires
     superuser, which the App SP lacks. If that fails, the migration logs
     a NOTICE and continues. The `add-entity` skill documents the
     belt-and-suspenders ALTER that new table migrations should include.

Configure CDF in the Lakebase UI (Branch overview → Change Data Feed →
Start) after this migration runs. See README and AGENTS.md.
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

    # Global event trigger registration. Requires superuser. The App SP
    # (CAN_CONNECT_AND_CREATE) does not have it; the catch makes this
    # migration safe to run regardless.
    op.execute(f"""
        DO $body$
        BEGIN
            EXECUTE $stmt$
                CREATE EVENT TRIGGER set_full_replica_identity_on_create
                ON ddl_command_end
                WHEN TAG IN ('CREATE TABLE')
                EXECUTE FUNCTION "{SCHEMA}".set_full_replica_identity()
            $stmt$;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE
                    'Skipping CREATE EVENT TRIGGER: current role lacks superuser. '
                    'New tables must include explicit ALTER TABLE ... REPLICA IDENTITY FULL '
                    'in their migrations. See the add-entity skill.';
            WHEN duplicate_object THEN
                NULL;
        END $body$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $body$
        BEGIN
            EXECUTE 'DROP EVENT TRIGGER IF EXISTS set_full_replica_identity_on_create';
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'Cannot drop event trigger without superuser; leaving it in place.';
        END $body$;
    """)
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
