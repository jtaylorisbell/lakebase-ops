"""Install the CDF auto-REPLICA-IDENTITY-FULL event trigger.

Runs as the deploying identity (project owner / `databricks_superuser`),
NOT as the App SP. Creating event triggers is a database-level operation
that requires superuser; the App SP intentionally doesn't have it.

Idempotent — drops and recreates the event trigger every time.

Run via `make install-cdf-trigger`, or directly:

    LAKEBASE_PROJECT_ID=... LAKEBASE_BRANCH_ID=... LAKEBASE_SCHEMA=... \
      uv run python scripts/install_cdf_event_trigger.py

The companion function `"{schema}".set_full_replica_identity()` is
created by alembic migration 0002 (the App SP owns the function in its
own schema; this script only handles the database-level trigger).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `backend` importable when run as `python scripts/...`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.config import SCHEMA, LakebaseSettings  # noqa: E402

TRIGGER_NAME = "set_full_replica_identity_on_create"


def main() -> None:
    settings = LakebaseSettings()
    engine = create_engine(settings.get_database_url())

    with engine.begin() as conn:
        # Make sure the function the trigger calls actually exists. If
        # someone runs this script before alembic has applied 0002, fail
        # loud rather than installing a trigger that calls a missing
        # function on every CREATE TABLE.
        exists = conn.execute(
            text(f"""
                SELECT 1
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = '{SCHEMA}'
                  AND p.proname = 'set_full_replica_identity'
            """)
        ).first()
        if not exists:
            raise RuntimeError(
                f'Function "{SCHEMA}".set_full_replica_identity() does not exist. '
                "Run alembic upgrade head (which applies migration 0002) before "
                "installing the event trigger."
            )

        conn.execute(text(f'DROP EVENT TRIGGER IF EXISTS {TRIGGER_NAME}'))
        conn.execute(
            text(f"""
                CREATE EVENT TRIGGER {TRIGGER_NAME}
                ON ddl_command_end
                WHEN TAG IN ('CREATE TABLE')
                EXECUTE FUNCTION "{SCHEMA}".set_full_replica_identity()
            """)
        )

    print(
        f"Installed event trigger {TRIGGER_NAME!r}; "
        f'future CREATE TABLE statements will auto-apply REPLICA IDENTITY FULL.'
    )


if __name__ == "__main__":
    main()
