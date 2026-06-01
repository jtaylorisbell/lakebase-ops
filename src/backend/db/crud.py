"""CRUD helpers for the todos table."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.schemas import Todo

_PRIORITY_ORDER = {"high": 1, "medium": 2, "low": 3}


def _priority_order(priority: str) -> int:
    return _PRIORITY_ORDER.get(priority, 2)


def create_todo(
    session: Session,
    *,
    title: str,
    description: str | None,
    priority: str,
    due_date: date | None,
    user_email: str | None,
) -> Todo:
    todo = Todo(
        title=title,
        description=description,
        priority=priority,
        priority_order=_priority_order(priority),
        due_date=due_date,
        user_email=user_email,
    )
    session.add(todo)
    session.commit()
    session.refresh(todo)
    return todo


def get_todo(session: Session, todo_id: str) -> Todo | None:
    return session.get(Todo, todo_id)


def list_todos(
    session: Session,
    *,
    user_email: str | None,
    completed: bool | None,
    limit: int,
) -> list[Todo]:
    stmt = select(Todo)
    if user_email is not None:
        stmt = stmt.where(Todo.user_email == user_email)
    if completed is not None:
        stmt = stmt.where(Todo.completed == completed)
    stmt = stmt.order_by(Todo.completed, Todo.priority_order, Todo.created_at.desc()).limit(limit)
    return list(session.scalars(stmt))


def update_todo(
    session: Session,
    todo_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    completed: bool | None = None,
    priority: str | None = None,
    due_date: date | None = None,
) -> Todo | None:
    todo = session.get(Todo, todo_id)
    if todo is None:
        return None
    if title is not None:
        todo.title = title
    if description is not None:
        todo.description = description
    if completed is not None:
        todo.completed = completed
    if priority is not None:
        todo.priority = priority
        todo.priority_order = _priority_order(priority)
    if due_date is not None:
        todo.due_date = due_date
    session.commit()
    session.refresh(todo)
    return todo


def toggle_todo(session: Session, todo_id: str) -> Todo | None:
    todo = session.get(Todo, todo_id)
    if todo is None:
        return None
    todo.completed = not todo.completed
    session.commit()
    session.refresh(todo)
    return todo


def delete_todo(session: Session, todo_id: str) -> bool:
    todo = session.get(Todo, todo_id)
    if todo is None:
        return False
    session.delete(todo)
    session.commit()
    return True


def get_stats(session: Session, *, user_email: str | None) -> dict[str, int]:
    base = select(Todo)
    if user_email is not None:
        base = base.where(Todo.user_email == user_email)

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    completed = (
        session.scalar(
            select(func.count()).select_from(base.where(Todo.completed.is_(True)).subquery())
        )
        or 0
    )
    high_priority = (
        session.scalar(
            select(func.count()).select_from(
                base.where(Todo.priority == "high", Todo.completed.is_(False)).subquery()
            )
        )
        or 0
    )
    return {
        "total": total,
        "completed": completed,
        "pending": total - completed,
        "high_priority": high_priority,
    }
