"""Database engine and session factory helpers."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from market_screener.core.settings import Settings, get_settings

SessionFactory = Callable[[], Session]


def create_engine_from_settings(settings: Settings | None = None) -> Engine:
    """Create SQLAlchemy engine using runtime settings."""

    resolved = settings or get_settings()
    return create_engine(resolved.sqlalchemy_database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> SessionFactory:
    """Create a session factory bound to the provided engine."""

    session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )

    def _factory() -> Session:
        return session_local()

    return _factory


def create_session_factory_from_settings(
    settings: Settings | None = None,
) -> SessionFactory:
    """Create session factory directly from runtime settings."""

    engine = create_engine_from_settings(settings)
    return create_session_factory(engine)
