---
name: add-entity
description: Add a new persisted entity (model + migration + CRUD + API + frontend types) end-to-end, mirroring the existing Todo pattern.
trigger: User asks to add a new entity, table, resource, or model — anything that needs to be created/read/updated/deleted via the API and persisted in Lakebase.
---

# Add a new entity

The Todo entity is the reference. Mirror it for any new entity (call the new one `Foo` in this recipe). All seven files are required — partial implementations don't work end-to-end.

## 1. Alembic migration — `alembic/versions/NNNN_add_foos.py`

Generate with `uv run alembic revision -m "add_foos"`, then fill in `upgrade()` / `downgrade()`. Use `schema=SCHEMA` on `create_table` and every `create_index`. Mirror `alembic/versions/0001_initial_schema.py`:

- `gen_random_uuid()` primary key.
- `created_at` / `updated_at` columns with `server_default=sa.text("now()")` and a `set_updated_at` trigger if you want the timestamp to advance on update (reuse the function defined in 0001 — `"{SCHEMA}".set_updated_at()`).
- Indexes for every column you'll filter by.
- **`op.execute(f'ALTER TABLE "{SCHEMA}".foos REPLICA IDENTITY FULL')` right after `create_table`.** Belt-and-suspenders for Lakebase CDF. The deploy-time event trigger (installed by `make install-cdf-trigger`) usually handles this automatically, but include the explicit ALTER so the migration is correct even if it's applied somewhere the trigger isn't installed (a fresh dev branch before `install-cdf-trigger` ran, a local psql session, etc.).
- `downgrade()` drops everything `upgrade()` created, including triggers and indexes.

Run `uv run alembic upgrade head` against your branch to apply it locally. (Or just restart the deployed app; it migrates on startup.)

## 2. SQLAlchemy model — `src/backend/db/schemas.py`

Add a `Foo(Base)` class next to `Todo`. The schema is set via `__table_args__`:

```python
__table_args__ = (
    Index("idx_foos_…", "…"),
    {"schema": SCHEMA},
)
```

Use `Mapped[T]` and `mapped_column(...)`. UUID primary key gets both `server_default=text("gen_random_uuid()")` and a Python-side `default=lambda: str(uuid4())` so newly constructed rows have an id before flush.

## 3. CRUD functions — `src/backend/db/crud.py`

Mirror the Todo functions: `create_foo`, `get_foo`, `list_foos`, `update_foo`, `delete_foo`. Each takes a `Session` and any kwargs the request needs. Always `session.commit()` after mutating; `session.refresh(obj)` after writes that return the row.

`list_*` should accept the filter columns and a `limit`, build a `select()` chain conditionally, and return `list(session.scalars(stmt))`.

## 4. Pydantic request/response — `src/backend/api/schemas.py`

Add `CreateFooRequest`, `UpdateFooRequest` (all fields optional), `FooResponse` (with `model_config = {"from_attributes": True}` so it can serialize from an ORM instance), and `FooListResponse({ foos, total })` if you have a list endpoint.

## 5. FastAPI routes — `src/backend/api/main.py`

Add routes under `/api/foos`. Every handler takes `session: Session = Depends(get_session)`. Use the user from `get_current_user(request)` when the entity is per-user. Return `FooResponse.model_validate(obj)` for single objects. 404 with `HTTPException(status_code=404, detail="Foo not found")` when `crud.*` returns `None` / `False`.

## 6. Frontend types — `frontend/src/types/api.ts`

Add a `Foo` interface and `CreateFooRequest` / `UpdateFooRequest` mirrors of the Pydantic shapes. Use the same field names — the API serializes Python snake_case directly.

## 7. Frontend client — `frontend/src/api/client.ts`

Extend the `api` object with `foos: { list, create, update, delete, ... }` following the existing `todos` pattern. The base path is `/api/foos`.

## Verify

- `uv run ruff check`
- `uv run pytest`
- `uv run python -c "from backend.api.main import app; print([r.path for r in app.routes if hasattr(r,'path')])"` — confirm the new routes are registered.
- Hit one of the new endpoints against a running backend (`make migrate` first if you haven't applied the migration).

## Anti-patterns

- Don't put DDL outside alembic — the App SP can only read/write objects it created via migrations.
- Don't skip the `{"schema": SCHEMA}` table arg — defaults land in `public` where the App SP has no permissions.
- Don't reach for `session.execute(text(...))` raw SQL when a typed `select(Foo)` works. The `LakebaseSettings`-backed engine already sets `search_path={SCHEMA}`, but ORM queries qualify the schema explicitly which is more robust.
