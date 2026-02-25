"""add data api support

Revision ID: a3b7c9d2e4f1
Revises: 8769141e5ee7
Create Date: 2026-02-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b7c9d2e4f1"
down_revision: str | None = "8769141e5ee7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. updated_at trigger ---
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_todos_updated_at
        BEFORE UPDATE ON todos
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)

    # --- 2. priority_order column + trigger ---
    op.add_column(
        "todos",
        sa.Column(
            "priority_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2"),
        ),
    )
    # Backfill existing rows
    op.execute("""
        UPDATE todos SET priority_order = CASE priority
            WHEN 'high' THEN 1
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 3
            ELSE 2
        END;
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION set_priority_order()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.priority_order = CASE NEW.priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 2
            END;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_todos_priority_order
        BEFORE INSERT OR UPDATE OF priority ON todos
        FOR EACH ROW
        EXECUTE FUNCTION set_priority_order();
    """)

    # --- 3. RPC functions ---
    op.execute("""
        CREATE OR REPLACE FUNCTION toggle_todo(todo_id UUID)
        RETURNS SETOF todos
        LANGUAGE sql
        SECURITY INVOKER
        AS $$
            UPDATE todos
            SET completed = NOT completed
            WHERE id = todo_id
            RETURNING *;
        $$;
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION todo_stats()
        RETURNS TABLE(
            total BIGINT,
            completed BIGINT,
            pending BIGINT,
            high_priority BIGINT
        )
        LANGUAGE sql
        SECURITY INVOKER
        AS $$
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE completed = true) AS completed,
                COUNT(*) FILTER (WHERE completed = false) AS pending,
                COUNT(*) FILTER (WHERE priority = 'high' AND completed = false) AS high_priority
            FROM todos;
        $$;
    """)

    # --- 4. Row Level Security ---
    op.execute("ALTER TABLE todos ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY todos_select ON todos
        FOR SELECT USING (user_email = current_user);
    """)
    op.execute("""
        CREATE POLICY todos_insert ON todos
        FOR INSERT WITH CHECK (user_email = current_user);
    """)
    op.execute("""
        CREATE POLICY todos_update ON todos
        FOR UPDATE USING (user_email = current_user);
    """)
    op.execute("""
        CREATE POLICY todos_delete ON todos
        FOR DELETE USING (user_email = current_user);
    """)

    # --- 5. Grants for Data API ---
    op.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth;")
    op.execute("GRANT USAGE ON SCHEMA public TO PUBLIC;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON todos TO PUBLIC;")
    op.execute("GRANT EXECUTE ON FUNCTION toggle_todo(UUID) TO PUBLIC;")
    op.execute("GRANT EXECUTE ON FUNCTION todo_stats() TO PUBLIC;")


def downgrade() -> None:
    # Revoke grants
    op.execute("REVOKE EXECUTE ON FUNCTION todo_stats() FROM PUBLIC;")
    op.execute("REVOKE EXECUTE ON FUNCTION toggle_todo(UUID) FROM PUBLIC;")
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON todos FROM PUBLIC;")
    op.execute("REVOKE USAGE ON SCHEMA public FROM PUBLIC;")

    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS todos_delete ON todos;")
    op.execute("DROP POLICY IF EXISTS todos_update ON todos;")
    op.execute("DROP POLICY IF EXISTS todos_insert ON todos;")
    op.execute("DROP POLICY IF EXISTS todos_select ON todos;")
    op.execute("ALTER TABLE todos DISABLE ROW LEVEL SECURITY;")

    # Drop RPC functions
    op.execute("DROP FUNCTION IF EXISTS todo_stats();")
    op.execute("DROP FUNCTION IF EXISTS toggle_todo(UUID);")

    # Drop priority_order
    op.execute("DROP TRIGGER IF EXISTS trg_todos_priority_order ON todos;")
    op.execute("DROP FUNCTION IF EXISTS set_priority_order();")
    op.drop_column("todos", "priority_order")

    # Drop updated_at trigger
    op.execute("DROP TRIGGER IF EXISTS trg_todos_updated_at ON todos;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
