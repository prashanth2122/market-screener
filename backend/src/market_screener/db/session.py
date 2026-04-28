"""Database engine and session factory helpers."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from market_screener.core.settings import Settings, get_settings
from market_screener.db.slow_query_profiler import install_slow_query_profiler

SessionFactory = Callable[[], Session]


def create_engine_from_settings(settings: Settings | None = None) -> Engine:
    """Create SQLAlchemy engine using runtime settings."""

    resolved = settings or get_settings()
    return _cached_engine(
        resolved.sqlalchemy_database_url,
        slow_query_enabled=bool(resolved.db_slow_query_log_enabled),
        slow_query_threshold_ms=int(resolved.db_slow_query_threshold_ms),
        slow_query_max_entries=int(resolved.db_slow_query_max_entries),
        slow_query_max_sql_chars=int(resolved.db_slow_query_max_sql_chars),
    )


@lru_cache
def _cached_engine(
    sqlalchemy_url: str,
    *,
    slow_query_enabled: bool,
    slow_query_threshold_ms: int,
    slow_query_max_entries: int,
    slow_query_max_sql_chars: int,
) -> Engine:
    engine = create_engine(sqlalchemy_url, pool_pre_ping=True)
    if slow_query_enabled:
        install_slow_query_profiler(
            engine,
            threshold_ms=slow_query_threshold_ms,
            max_entries=slow_query_max_entries,
            max_sql_chars=slow_query_max_sql_chars,
        )
    return engine


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
