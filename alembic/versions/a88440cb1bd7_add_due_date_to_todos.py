"""add_due_date_to_todos

Revision ID: a88440cb1bd7
Revises: a3b7c9d2e4f1
Create Date: 2026-03-05 14:55:11.675014

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a88440cb1bd7'
down_revision: Union[str, None] = 'a3b7c9d2e4f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("due_date", sa.Date(), nullable=True))
    op.create_index("idx_todos_due_date", "todos", ["due_date"])


def downgrade() -> None:
    op.drop_index("idx_todos_due_date", table_name="todos")
    op.drop_column("todos", "due_date")
