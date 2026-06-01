"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from backend.config import SCHEMA

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    op.create_table(
        "todos",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("priority", sa.Text(), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("priority_order", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("user_email", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index("idx_todos_user_email", "todos", ["user_email"], schema=SCHEMA)
    op.create_index("idx_todos_completed", "todos", ["completed"], schema=SCHEMA)
    op.create_index("idx_todos_created_at", "todos", ["created_at"], schema=SCHEMA)
    op.create_index("idx_todos_due_date", "todos", ["due_date"], schema=SCHEMA)

    op.execute(f"""
        CREATE OR REPLACE FUNCTION "{SCHEMA}".set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute(f"""
        CREATE TRIGGER trg_todos_updated_at
        BEFORE UPDATE ON "{SCHEMA}".todos
        FOR EACH ROW
        EXECUTE FUNCTION "{SCHEMA}".set_updated_at();
    """)
    op.execute(f"""
        CREATE OR REPLACE FUNCTION "{SCHEMA}".set_priority_order()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.priority_order = CASE NEW.priority
                WHEN 'high'   THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low'    THEN 3
                ELSE 2
            END;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute(f"""
        CREATE TRIGGER trg_todos_priority_order
        BEFORE INSERT OR UPDATE OF priority ON "{SCHEMA}".todos
        FOR EACH ROW
        EXECUTE FUNCTION "{SCHEMA}".set_priority_order();
    """)


def downgrade() -> None:
    op.execute(f'DROP TRIGGER IF EXISTS trg_todos_priority_order ON "{SCHEMA}".todos')
    op.execute(f'DROP FUNCTION IF EXISTS "{SCHEMA}".set_priority_order()')
    op.execute(f'DROP TRIGGER IF EXISTS trg_todos_updated_at ON "{SCHEMA}".todos')
    op.execute(f'DROP FUNCTION IF EXISTS "{SCHEMA}".set_updated_at()')
    op.drop_index("idx_todos_due_date", table_name="todos", schema=SCHEMA)
    op.drop_index("idx_todos_created_at", table_name="todos", schema=SCHEMA)
    op.drop_index("idx_todos_completed", table_name="todos", schema=SCHEMA)
    op.drop_index("idx_todos_user_email", table_name="todos", schema=SCHEMA)
    op.drop_table("todos", schema=SCHEMA)
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}"')
