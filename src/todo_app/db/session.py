"""SQLAlchemy session factory backed by a Lakebase OAuth token."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from todo_app.config import LakebaseSettings


def _build_engine() -> Engine:
    settings = LakebaseSettings()
    engine = create_engine(
        settings.get_database_url(),
        pool_pre_ping=True,
        pool_recycle=1800,
    )

    @event.listens_for(engine, "do_connect")
    def _refresh_password(_dialect, _conn_rec, cargs, cparams):  # noqa: ANN001
        cparams["password"] = settings.get_password()

    return engine


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def session_factory() -> sessionmaker[Session]:
    global _engine, _session_factory
    if _session_factory is None:
        _engine = _build_engine()
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _session_factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a SQLAlchemy session."""
    with session_factory()() as session:
        yield session
