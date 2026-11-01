"""Per symbol/day market data audit pipeline tests (Layer 4)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from finpilot.data import (
    AuditVerdict,
    DataAnomalyType,
    MarketDataAuditor,
    SyntheticDataProviderAdapter,
)

IST = ZoneInfo("Asia/Kolkata")


def test_audit_clean_session_passes() -> None:
    adapter = SyntheticDataProviderAdapter()
    trading_day = date(2026, 10, 30)
    bars = adapter.fetch_bars("RELIANCE", trading_day)

    auditor = MarketDataAuditor()
    report = auditor.audit_session(
        symbol="RELIANCE",
        audit_date=trading_day,
        records=bars,
        previous_session_close=Decimal("2500.0000"),
    )

    assert report.symbol == "RELIANCE"
    assert report.audit_date == trading_day
    assert report.session_expected_bars == 75
    assert report.total_bars == 75
    assert report.valid_bars == 75
    assert report.quarantined_bars == 0
    assert report.missing_bars == 0
    assert report.completion_pct == 100.0
    assert report.quality_score >= 0.95
    assert report.verdict == AuditVerdict.PASS


def test_audit_detects_session_misalignment_and_weekends() -> None:
    auditor = MarketDataAuditor()

    # 1. Weekend trading date
    weekend_date = date(2026, 10, 31)  # Saturday
    report_wknd = auditor.audit_session(
        symbol="RELIANCE",
        audit_date=weekend_date,
        records=[],
    )
    assert any(
        a.anomaly_type == DataAnomalyType.SESSION_MISALIGNMENT for a in report_wknd.anomalies
    )

    # 2. Out-of-session hours (08:30 IST)
    dt_early = datetime(2026, 10, 30, 8, 30, 0, tzinfo=IST).astimezone(UTC)
    adapter = SyntheticDataProviderAdapter()
    valid_bars = list(adapter.fetch_bars("RELIANCE", date(2026, 10, 30))[:5])
    bad_bar = valid_bars[0].model_copy(update={"timestamp": dt_early})

    report_early = auditor.audit_session(
        symbol="RELIANCE",
        audit_date=date(2026, 10, 30),
        records=[bad_bar],
    )
    assert any(
        a.anomaly_type == DataAnomalyType.SESSION_MISALIGNMENT for a in report_early.anomalies
    )


def test_audit_detects_duplicates_and_out_of_order_bars() -> None:
    adapter = SyntheticDataProviderAdapter()
    bars = list(adapter.fetch_bars("RELIANCE", date(2026, 10, 30))[:5])

    # Insert duplicate bar
    bars_with_dup = [bars[0], bars[0], bars[1], bars[2]]
    auditor = MarketDataAuditor()
    report_dup = auditor.audit_session(
        symbol="RELIANCE",
        audit_date=date(2026, 10, 30),
        records=bars_with_dup,
    )
    assert any(a.anomaly_type == DataAnomalyType.DUPLICATE_BAR for a in report_dup.anomalies)
    assert report_dup.quarantined_bars >= 1

    # Insert out-of-order bar
    bars_out_of_order = [bars[1], bars[0], bars[2]]
    report_order = auditor.audit_session(
        symbol="RELIANCE",
        audit_date=date(2026, 10, 30),
        records=bars_out_of_order,
    )
    assert any(a.anomaly_type == DataAnomalyType.OUT_OF_ORDER_BAR for a in report_order.anomalies)


def test_audit_detects_ohlc_inconsistencies_and_non_finite_values() -> None:
    adapter = SyntheticDataProviderAdapter()
    bars = list(adapter.fetch_bars("RELIANCE", date(2026, 10, 30))[:3])

    # High < Open
    bad_ohlc = bars[0].model_copy(
        update={"open": Decimal("2550.0000"), "high": Decimal("2500.0000")}
    )
    auditor = MarketDataAuditor()
    report = auditor.audit_session(
        symbol="RELIANCE",
        audit_date=date(2026, 10, 30),
        records=[bad_ohlc],
    )
    assert any(a.anomaly_type == DataAnomalyType.OHLC_INCONSISTENCY for a in report.anomalies)
    assert report.verdict == AuditVerdict.REJECTED


def test_audit_detects_suspicious_price_jumps_and_corporate_actions() -> None:
    adapter = SyntheticDataProviderAdapter()
    bars = list(adapter.fetch_bars("RELIANCE", date(2026, 10, 30))[:5])

    # 1. Single bar jump > 10%
    jump_bar = bars[0].model_copy(
        update={
            "open": Decimal("2500.0000"),
            "high": Decimal("2800.0000"),
            "close": Decimal("2780.0000"),  # > 11% jump
        }
    )
    auditor = MarketDataAuditor()
    report_jump = auditor.audit_session(
        symbol="RELIANCE",
        audit_date=date(2026, 10, 30),
        records=[jump_bar],
    )
    assert any(
        a.anomaly_type == DataAnomalyType.SUSPICIOUS_PRICE_JUMP for a in report_jump.anomalies
    )

    # 2. Corporate action gap > 20% from previous close
    report_gap = auditor.audit_session(
        symbol="RELIANCE",
        audit_date=date(2026, 10, 30),
        records=bars,
        previous_session_close=Decimal("2000.0000"),  # 25% gap to 2500
    )
    assert any(a.anomaly_type == DataAnomalyType.CORPORATE_ACTION_GAP for a in report_gap.anomalies)


def test_audit_cross_source_check() -> None:
    adapter = SyntheticDataProviderAdapter()
    primary = list(adapter.fetch_bars("RELIANCE", date(2026, 10, 30))[:5])

    # Reference with a 2% deviation on bar 2
    reference = [
        primary[0],
        primary[1],
        primary[2].model_copy(update={"close": primary[2].close * Decimal("1.02")}),
        primary[3],
        primary[4],
    ]

    auditor = MarketDataAuditor()
    discrepancies = auditor.cross_source_check(primary, reference)
    assert len(discrepancies) == 1
    assert discrepancies[0].anomaly_type == DataAnomalyType.CROSS_SOURCE_DISCREPANCY
    assert "delta=" in discrepancies[0].description
