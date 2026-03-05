"""Pydantic request/response schemas for Todo App API."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from todo_app.core.models import Priority


class CreateTodoRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    priority: Priority = Priority.MEDIUM
    due_date: date | None = None


class UpdateTodoRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    completed: bool | None = None
    priority: Priority | None = None
    due_date: date | None = None


class TodoResponse(BaseModel):
    id: str
    title: str
    description: str | None
    completed: bool
    priority: Priority
    due_date: date | None = None
    user_email: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TodoListResponse(BaseModel):
    todos: list[TodoResponse]
    total: int


class TodoStatsResponse(BaseModel):
    total: int
    completed: int
    pending: int
    high_priority: int


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


class CurrentUserResponse(BaseModel):
    email: str | None
    name: str | None
    display_name: str
    is_authenticated: bool
