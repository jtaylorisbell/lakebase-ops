"""FastAPI application for Todo App."""

from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend import __version__
from backend.api.schemas import (
    CreateTodoRequest,
    CurrentUserResponse,
    HealthResponse,
    TodoListResponse,
    TodoResponse,
    TodoStatsResponse,
    UpdateTodoRequest,
)
from backend.api.user import get_current_user
from backend.db import crud
from backend.db.session import get_session

logger = structlog.get_logger()


app = FastAPI(
    title="Lakebase Todo App API",
    description="A To-Do list powered by Databricks Apps and Lakebase",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health(session: Session = Depends(get_session)) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        logger.error("health_check_failed", error=str(exc))
        db_status = "disconnected"
    return HealthResponse(status="ok", version=__version__, database=db_status)


@app.get("/api/me", response_model=CurrentUserResponse)
async def get_me(request: Request) -> CurrentUserResponse:
    user = get_current_user(request)
    return CurrentUserResponse(
        email=user.email,
        name=user.name,
        display_name=user.display_name,
        is_authenticated=user.is_authenticated,
    )


@app.post("/api/todos", response_model=TodoResponse, status_code=201)
async def create_todo(
    body: CreateTodoRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TodoResponse:
    user = get_current_user(request)
    todo = crud.create_todo(
        session,
        title=body.title,
        description=body.description,
        priority=body.priority.value,
        due_date=body.due_date,
        user_email=user.email,
    )
    return TodoResponse.model_validate(todo)


@app.get("/api/todos", response_model=TodoListResponse)
async def list_todos(
    request: Request,
    completed: bool | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> TodoListResponse:
    user = get_current_user(request)
    todos = crud.list_todos(session, user_email=user.email, completed=completed, limit=limit)
    return TodoListResponse(
        todos=[TodoResponse.model_validate(t) for t in todos],
        total=len(todos),
    )


@app.get("/api/todos/{todo_id}", response_model=TodoResponse)
async def get_todo(todo_id: str, session: Session = Depends(get_session)) -> TodoResponse:
    todo = crud.get_todo(session, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse.model_validate(todo)


@app.put("/api/todos/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: str,
    body: UpdateTodoRequest,
    session: Session = Depends(get_session),
) -> TodoResponse:
    todo = crud.update_todo(
        session,
        todo_id,
        title=body.title,
        description=body.description,
        completed=body.completed,
        priority=body.priority.value if body.priority else None,
        due_date=body.due_date,
    )
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse.model_validate(todo)


@app.patch("/api/todos/{todo_id}/toggle", response_model=TodoResponse)
async def toggle_todo(todo_id: str, session: Session = Depends(get_session)) -> TodoResponse:
    todo = crud.toggle_todo(session, todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse.model_validate(todo)


@app.delete("/api/todos/{todo_id}", status_code=204)
async def delete_todo(todo_id: str, session: Session = Depends(get_session)) -> None:
    if not crud.delete_todo(session, todo_id):
        raise HTTPException(status_code=404, detail="Todo not found")


@app.get("/api/stats", response_model=TodoStatsResponse)
async def get_stats(
    request: Request,
    session: Session = Depends(get_session),
) -> TodoStatsResponse:
    user = get_current_user(request)
    return TodoStatsResponse(**crud.get_stats(session, user_email=user.email))


_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
