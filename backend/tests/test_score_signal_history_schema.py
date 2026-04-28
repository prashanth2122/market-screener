"""Tests for score and signal history schema design constraints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from market_screener.db.models.core import Asset, ScoreHistory, SignalHistory


def test_score_and_signal_history_persist_expected_fields() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    ScoreHistory.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_local() as session:
        asset = Asset(
            symbol="AAPL",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.flush()

        as_of = datetime(2026, 4, 23, 14, 0, tzinfo=UTC)
        session.add(
            ScoreHistory(
                asset_id=asset.id,
                as_of_ts=as_of,
                model_version="v1.0.1",
                composite_score=Decimal("74.9721"),
                technical_score=Decimal("79.9100"),
                fundamental_score=Decimal("77.5000"),
                sentiment_risk_score=Decimal("62.0000"),
                details={"unavailable_components": []},
            )
        )
        session.add(
            SignalHistory(
                asset_id=asset.id,
                as_of_ts=as_of,
                model_version="v1.0.1",
                signal="buy",
                score=Decimal("74.9721"),
                confidence=Decimal("0.9100"),
                blocked_by_risk=False,
                reasons=["score_bucket=buy"],
                details={"label": "Buy"},
            )
        )
        session.commit()

    with session_local() as session:
        score_row = session.scalar(select(ScoreHistory))
        signal_row = session.scalar(select(SignalHistory))

    assert score_row is not None
    assert float(score_row.composite_score) == 74.9721
    assert score_row.model_version == "v1.0.1"
    assert score_row.details == {"unavailable_components": []}

    assert signal_row is not None
    assert signal_row.signal == "buy"
    assert float(signal_row.score or 0) == 74.9721
    assert float(signal_row.confidence or 0) == 0.91
    assert signal_row.reasons == ["score_bucket=buy"]


def test_score_history_unique_constraint_blocks_duplicates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    ScoreHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    asset_id: int
    with session_local() as session:
        asset = Asset(
            symbol="MSFT",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.flush()
        asset_id = asset.id
        as_of = datetime(2026, 4, 23, 14, 0, tzinfo=UTC)
        session.add(
            ScoreHistory(
                asset_id=asset.id,
                as_of_ts=as_of,
                model_version="v1.0.1",
                composite_score=Decimal("69.1200"),
            )
        )
        session.commit()

    with session_local() as session:
        session.add(
            ScoreHistory(
                asset_id=asset_id,
                as_of_ts=datetime(2026, 4, 23, 14, 0, tzinfo=UTC),
                model_version="v1.0.1",
                composite_score=Decimal("70.0000"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_signal_history_unique_constraint_blocks_duplicates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    asset_id: int
    with session_local() as session:
        asset = Asset(
            symbol="NVDA",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.flush()
        asset_id = asset.id
        as_of = datetime(2026, 4, 23, 14, 0, tzinfo=UTC)
        session.add(
            SignalHistory(
                asset_id=asset.id,
                as_of_ts=as_of,
                model_version="v1.0.1",
                signal="buy",
            )
        )
        session.commit()

    with session_local() as session:
        session.add(
            SignalHistory(
                asset_id=asset_id,
                as_of_ts=datetime(2026, 4, 23, 14, 0, tzinfo=UTC),
                model_version="v1.0.1",
                signal="watch",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_history_tables_allow_same_timestamp_for_different_model_versions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    ScoreHistory.__table__.create(engine)
    SignalHistory.__table__.create(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    as_of = datetime(2026, 4, 23, 14, 0, tzinfo=UTC)
    with session_local() as session:
        asset = Asset(
            symbol="AMZN",
            asset_type="equity",
            exchange="US",
            quote_currency="USD",
            active=True,
        )
        session.add(asset)
        session.flush()
        session.add_all(
            [
                ScoreHistory(
                    asset_id=asset.id,
                    as_of_ts=as_of,
                    model_version="v1.0.1",
                    composite_score=Decimal("71.0000"),
                ),
                ScoreHistory(
                    asset_id=asset.id,
                    as_of_ts=as_of,
                    model_version="v1.1.0",
                    composite_score=Decimal("72.0000"),
                ),
                SignalHistory(
                    asset_id=asset.id,
                    as_of_ts=as_of,
                    model_version="v1.0.1",
                    signal="buy",
                ),
                SignalHistory(
                    asset_id=asset.id,
                    as_of_ts=as_of,
                    model_version="v1.1.0",
                    signal="watch",
                ),
            ]
        )
        session.commit()

    with session_local() as session:
        score_rows = session.scalars(select(ScoreHistory)).all()
        signal_rows = session.scalars(select(SignalHistory)).all()
    assert len(score_rows) == 2
    assert len(signal_rows) == 2
