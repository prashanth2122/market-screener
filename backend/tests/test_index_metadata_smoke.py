"""Smoke tests to ensure new indexes are present in ORM metadata.

This does not validate query plans; it prevents accidental index drift between models and migrations.
"""

from __future__ import annotations

from market_screener.db.models.core import (
    Asset,
    FundamentalsSnapshot,
    IndicatorSnapshot,
    NewsEvent,
    Price,
    ScoreHistory,
    SignalHistory,
)


def _index_names(table) -> set[str]:
    return {index.name for index in table.indexes if index.name}


def test_core_tables_include_api_hot_path_indexes() -> None:
    assert "ix_assets_active_type_exchange_quote" in _index_names(Asset.__table__)
    assert "ix_signal_history_model_asset_asof" in _index_names(SignalHistory.__table__)
    assert "ix_signal_history_asset_model_asof" in _index_names(SignalHistory.__table__)
    assert "ix_score_history_asset_model_asof" in _index_names(ScoreHistory.__table__)
    assert "ix_prices_asset_source_ts" in _index_names(Price.__table__)
    assert "ix_indicators_snapshot_asset_source_ts" in _index_names(IndicatorSnapshot.__table__)
    assert "ix_fundamentals_snapshot_asset_source_period" in _index_names(
        FundamentalsSnapshot.__table__
    )
    assert "ix_news_events_asset_source_published" in _index_names(NewsEvent.__table__)
