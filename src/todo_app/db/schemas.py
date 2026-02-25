"""SQLAlchemy ORM models for Todo App."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Index, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Todo(Base):
    """A todo item."""

    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed: Mapped[bool] = mapped_column(default=False)
    priority: Mapped[str] = mapped_column(Text, default="medium")
    priority_order: Mapped[int] = mapped_column(default=2)
    user_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=_utc_now)

    __table_args__ = (
        Index("idx_todos_user_email", "user_email"),
        Index("idx_todos_completed", "completed"),
        Index("idx_todos_created_at", "created_at"),
    )
