"""SQLAlchemy ORM models for Todo App."""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.config import SCHEMA


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Todo(Base):
    __tablename__ = "todos"
    __table_args__ = (
        Index("idx_todos_user_email", "user_email"),
        Index("idx_todos_completed", "completed"),
        Index("idx_todos_created_at", "created_at"),
        Index("idx_todos_due_date", "due_date"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=lambda: str(uuid4()),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    priority_order: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    user_email: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)
