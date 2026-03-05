"""FastAPI application for Todo App."""

from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from todo_app import __version__
from todo_app.api.schemas import (
    CreateTodoRequest,
    CurrentUserResponse,
    HealthResponse,
    TodoListResponse,
    TodoResponse,
    TodoStatsResponse,
    UpdateTodoRequest,
)
from todo_app.api.user import get_current_user
from todo_app.db.data_api import get_data_api

logger = structlog.get_logger()


def _get_user_token(request: Request) -> str | None:
    """Extract the user's OAuth token injected by Databricks Apps proxy."""
    return request.headers.get("X-Forwarded-Access-Token")


app = FastAPI(
    title="Lakebase Todo App API",
    description="A beautiful To-Do list powered by Databricks Apps and Lakebase",
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
async def health(request: Request) -> HealthResponse:
    token = _get_user_token(request)
    api = get_data_api()
    db_status = "connected" if api.health_check(user_token=token) else "disconnected"
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
async def create_todo(body: CreateTodoRequest, request: Request) -> TodoResponse:
    user = get_current_user(request)
    token = _get_user_token(request)
    api = get_data_api()
    todo = api.create_todo(
        title=body.title,
        description=body.description,
        priority=body.priority.value,
        due_date=body.due_date.isoformat() if body.due_date else None,
        user_email=user.email,
        user_token=token,
    )
    return TodoResponse(**todo)


@app.get("/api/todos", response_model=TodoListResponse)
async def list_todos(
    completed: bool | None = None,
    limit: int = 100,
    request: Request = None,
) -> TodoListResponse:
    token = _get_user_token(request)
    api = get_data_api()
    # RLS handles user filtering automatically via the forwarded token
    todos = api.list_todos(completed=completed, limit=limit, user_token=token)
    return TodoListResponse(
        todos=[TodoResponse(**t) for t in todos],
        total=len(todos),
    )


@app.get("/api/todos/{todo_id}", response_model=TodoResponse)
async def get_todo(todo_id: str, request: Request) -> TodoResponse:
    token = _get_user_token(request)
    api = get_data_api()
    todo = api.get_todo(todo_id, user_token=token)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse(**todo)


@app.put("/api/todos/{todo_id}", response_model=TodoResponse)
async def update_todo(
    todo_id: str, body: UpdateTodoRequest, request: Request
) -> TodoResponse:
    token = _get_user_token(request)
    api = get_data_api()
    todo = api.update_todo(
        todo_id,
        title=body.title,
        description=body.description,
        completed=body.completed,
        priority=body.priority.value if body.priority else None,
        due_date=body.due_date.isoformat() if body.due_date else None,
        user_token=token,
    )
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse(**todo)


@app.patch("/api/todos/{todo_id}/toggle", response_model=TodoResponse)
async def toggle_todo(todo_id: str, request: Request) -> TodoResponse:
    token = _get_user_token(request)
    api = get_data_api()
    todo = api.toggle_todo(todo_id, user_token=token)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo not found")
    return TodoResponse(**todo)


@app.delete("/api/todos/{todo_id}", status_code=204)
async def delete_todo(todo_id: str, request: Request):
    token = _get_user_token(request)
    api = get_data_api()
    if not api.delete_todo(todo_id, user_token=token):
        raise HTTPException(status_code=404, detail="Todo not found")


@app.get("/api/stats", response_model=TodoStatsResponse)
async def get_stats(request: Request) -> TodoStatsResponse:
    token = _get_user_token(request)
    api = get_data_api()
    # RLS handles user filtering automatically via the forwarded token
    stats = api.get_stats(user_token=token)
    return TodoStatsResponse(**stats)


def _find_project_root() -> Path:
    from_main = Path(__file__).parent.parent.parent.parent
    if (from_main / "frontend").exists():
        return from_main
    from_cwd = Path.cwd()
    if (from_cwd / "frontend").exists():
        return from_cwd
    return from_main


PROJECT_ROOT = _find_project_root()

frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    app.mount(
        "/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend"
    )
