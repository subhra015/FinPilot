"""Tests for point-in-time universe filtering and causal feature integrity (Layer 8).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2 (Point-in-Time Correctness)
- ARCHITECTURE.md §2, §5 (Stable Identity & Universe Snapshots)
- Layer 8 Gate: Use only point-in-time features and eligible universe membership;
  document unavailable survivorship/universe history as a limitation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.data.models import MarketDataRecord
from finpilot.db.enums import DataMode
from finpilot.features.models import FeatureVector
from finpilot.features.universe import PointInTimeUniverseManager
from finpilot.labeling.generator import TradePolicyLabelGenerator

IST = ZoneInfo("Asia/Kolkata")


def make_bar(
    symbol: str,
    ts_ist: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 10000,
    instrument_id: int = 1,
) -> MarketDataRecord:
    """Helper creating a valid completed 5-minute MarketDataRecord."""
    utc_ts = ts_ist.astimezone(ZoneInfo("UTC"))
    return MarketDataRecord(
        source="TEST_FEED",
        retrieval_time=utc_ts,
        instrument_id=instrument_id,
        symbol=symbol,
        exchange="NSE",
        timestamp=utc_ts,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
        mode=DataMode.HISTORICAL_REPLAY,
    )


def make_feature_vector(
    symbol: str,
    ts_ist: datetime,
    instrument_id: int = 1,
    is_warmed_up: bool = True,
) -> FeatureVector:
    """Helper creating a point-in-time FeatureVector."""
    utc_ts = ts_ist.astimezone(ZoneInfo("UTC"))
    return FeatureVector(
        instrument_id=instrument_id,
        symbol=symbol,
        timestamp=utc_ts,
        feature_set_version="FS-V1",
        features={
            "ret_1": 0.002,
            "sma_ratio_9_21": 0.005,
            "rsi_14": 58.5,
            "causal_rel_vol": 1.25,
        },
        is_fully_warmed_up=is_warmed_up,
        bar_count_in_session=25,
        mode=DataMode.HISTORICAL_REPLAY,
    )


def test_pit_universe_ineligibility_exclusion() -> None:
    """Verify that an instrument not yet listed at decision_time is excluded."""
    pit_mgr = PointInTimeUniverseManager()

    # Symbol A was listed in 2020 (active)
    pit_mgr.register_instrument(
        instrument_id=1,
        isin="INE002A01018",
        listing_date=datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")),
        symbol_history=[("RELIANCE", datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")), None)],
    )

    # Symbol B is listed in the future relative to January 2026 (e.g. March 2026)
    pit_mgr.register_instrument(
        instrument_id=2,
        isin="INE999B01099",
        listing_date=datetime(2026, 3, 1, tzinfo=ZoneInfo("UTC")),
        symbol_history=[("NEWCO", datetime(2026, 3, 1, tzinfo=ZoneInfo("UTC")), None)],
    )

    generator = TradePolicyLabelGenerator()
    eval_time = datetime(2026, 1, 15, 10, 0, tzinfo=IST)

    bars_newco = [
        make_bar("NEWCO", eval_time, 100.0, 102.0, 99.0, 101.0, instrument_id=2),
        make_bar(
            "NEWCO", eval_time + timedelta(minutes=5), 101.0, 103.0, 100.0, 102.0, instrument_id=2
        ),
        make_bar(
            "NEWCO", eval_time + timedelta(minutes=10), 102.0, 106.0, 101.0, 105.0, instrument_id=2
        ),
    ]
    feat_newco = {
        bars_newco[0].timestamp: make_feature_vector("NEWCO", eval_time, instrument_id=2)
    }

    # Generating labels with PIT manager must exclude NEWCO because it's not listed as of 2026-01-15
    labels, excluded_count = generator.generate_labels_for_series(
        instrument_id=2,
        symbol="NEWCO",
        bars=bars_newco,
        features_by_time=feat_newco,
        pit_universe_manager=pit_mgr,
    )

    assert len(labels) == 0
    assert excluded_count >= 1


def test_feature_warmup_and_cutoff_exclusions() -> None:
    """Verify that cold features (< warmup bars) and late bars (>= 15:00 IST) are excluded."""
    generator = TradePolicyLabelGenerator()

    # 1. Cold warmup candle
    cold_time = datetime(2026, 1, 15, 9, 30, tzinfo=IST)
    cold_bars = [
        make_bar("TCS", cold_time, 3500.0, 3510.0, 3495.0, 3505.0),
        make_bar("TCS", cold_time + timedelta(minutes=5), 3505.0, 3520.0, 3500.0, 3515.0),
    ]
    cold_feat = {cold_bars[0].timestamp: make_feature_vector("TCS", cold_time, is_warmed_up=False)}

    labels_cold, excl_cold = generator.generate_labels_for_series(1, "TCS", cold_bars, cold_feat)
    assert len(labels_cold) == 0
    assert excl_cold >= 1

    # 2. Session cutoff candle (>= 15:00 IST)
    late_time = datetime(2026, 1, 15, 15, 0, tzinfo=IST)
    late_bars = [
        make_bar("TCS", late_time, 3515.0, 3520.0, 3510.0, 3518.0),
        make_bar("TCS", late_time + timedelta(minutes=5), 3518.0, 3525.0, 3515.0, 3520.0),
    ]
    late_feat = {late_bars[0].timestamp: make_feature_vector("TCS", late_time, is_warmed_up=True)}

    labels_late, excl_late = generator.generate_labels_for_series(1, "TCS", late_bars, late_feat)
    assert len(labels_late) == 0
    assert excl_late >= 1


def test_future_candle_mutation_no_leakage() -> None:
    """Verify mutating future candles does not alter earlier features or decision timestamps."""
    generator = TradePolicyLabelGenerator()
    base_time = datetime(2026, 1, 15, 10, 0, tzinfo=IST)

    bars_orig = [
        make_bar("INFY", base_time, 1500.0, 1505.0, 1498.0, 1502.0),
        make_bar("INFY", base_time + timedelta(minutes=5), 1502.0, 1510.0, 1500.0, 1508.0),
        make_bar("INFY", base_time + timedelta(minutes=10), 1508.0, 1540.0, 1505.0, 1535.0),
    ]
    feat = {bars_orig[0].timestamp: make_feature_vector("INFY", base_time)}

    labels_orig, _ = generator.generate_labels_for_series(1, "INFY", bars_orig, feat)
    assert len(labels_orig) == 1

    # Mutate future candle at 10:10 (extreme high)
    bars_mutated = [
        bars_orig[0],
        bars_orig[1],
        make_bar("INFY", base_time + timedelta(minutes=10), 1508.0, 1800.0, 1505.0, 1790.0),
    ]

    labels_mutated, _ = generator.generate_labels_for_series(1, "INFY", bars_mutated, feat)
    assert len(labels_mutated) == 1

    # Invariants: decision time, entry time, entry price, and features must be identical!
    assert labels_orig[0].decision_time == labels_mutated[0].decision_time
    assert labels_orig[0].entry_time == labels_mutated[0].entry_time
    assert labels_orig[0].entry_price == labels_mutated[0].entry_price
    assert labels_orig[0].features == labels_mutated[0].features
