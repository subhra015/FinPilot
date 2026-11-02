"""Tests for point-in-time universe selection and historical symbol resolution (Layer 5)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from finpilot.features.universe import PointInTimeUniverseManager

IST = ZoneInfo("Asia/Kolkata")


def test_universe_survivorship_bias_prevention() -> None:
    """Delisted company must remain eligible for dates prior to its delisting."""
    mgr = PointInTimeUniverseManager()

    # Company delisted on 2024-01-01
    mgr.register_instrument(
        instrument_id=1,
        isin="INE001A01011",
        listing_date=datetime(2015, 1, 1, tzinfo=IST),
        delisting_date=datetime(2024, 1, 1, tzinfo=IST),
        status="ACTIVE",
        symbol_history=[("DELISTCORP", datetime(2015, 1, 1, tzinfo=IST), None)],
    )

    # Query before delisting (2023-06-01) -> Must be eligible!
    snap_before = mgr.get_point_in_time_universe(as_of=datetime(2023, 6, 1, 10, 0, tzinfo=IST))
    assert snap_before.eligible_count == 1
    assert snap_before.members[0].is_eligible is True
    assert snap_before.members[0].symbol == "DELISTCORP"

    # Query after delisting (2024-06-01) -> Ineligible!
    snap_after = mgr.get_point_in_time_universe(as_of=datetime(2024, 6, 1, 10, 0, tzinfo=IST))
    assert snap_after.eligible_count == 0
    assert snap_after.members[0].is_eligible is False
    assert "Delisted prior" in (snap_after.members[0].ineligibility_reason or "")


def test_universe_future_listing_lookahead_prevention() -> None:
    """Company listed in the future must NOT appear as eligible in historical snapshots."""
    mgr = PointInTimeUniverseManager()

    # IPO on 2024-06-01
    mgr.register_instrument(
        instrument_id=2,
        isin="INE002B02022",
        listing_date=datetime(2024, 6, 1, tzinfo=IST),
        delisting_date=None,
        status="ACTIVE",
        symbol_history=[("NEWIPO", datetime(2024, 6, 1, tzinfo=IST), None)],
    )

    # Query prior to IPO (2024-01-15) -> Ineligible!
    snap_prior = mgr.get_point_in_time_universe(as_of=datetime(2024, 1, 15, 10, 0, tzinfo=IST))
    assert snap_prior.eligible_count == 0
    assert snap_prior.members[0].is_eligible is False
    assert "Not yet listed" in (snap_prior.members[0].ineligibility_reason or "")

    # Query after IPO (2024-07-01) -> Eligible!
    snap_post = mgr.get_point_in_time_universe(as_of=datetime(2024, 7, 1, 10, 0, tzinfo=IST))
    assert snap_post.eligible_count == 1
    assert snap_post.members[0].is_eligible is True


def test_universe_historical_symbol_mapping() -> None:
    """Resolves point-in-time ticker symbols correctly across historical ticker changes."""
    mgr = PointInTimeUniverseManager()

    # Axis Bank renamed from UTI Bank on 2007-07-30
    rename_date = datetime(2007, 7, 30, tzinfo=IST)
    mgr.register_instrument(
        instrument_id=3,
        isin="INE238A01034",
        listing_date=datetime(1998, 1, 1, tzinfo=IST),
        symbol_history=[
            ("UTIBANK", datetime(1998, 1, 1, tzinfo=IST), rename_date),
            ("AXISBANK", rename_date, None),
        ],
    )

    # Query in 2005 -> UTIBANK
    sym_2005 = mgr.resolve_symbol_at(instrument_id=3, as_of=datetime(2005, 5, 1, tzinfo=IST))
    assert sym_2005 == "UTIBANK"

    # Query in 2010 -> AXISBANK
    sym_2010 = mgr.resolve_symbol_at(instrument_id=3, as_of=datetime(2010, 5, 1, tzinfo=IST))
    assert sym_2010 == "AXISBANK"


def test_universe_causal_liquidity_evaluation() -> None:
    """Historical liquidity check must strictly use sessions before the evaluation date."""
    mgr = PointInTimeUniverseManager()

    turnovers = {
        date(2026, 11, 2): 10_000_000.0,
        date(2026, 11, 3): 12_000_000.0,
        date(2026, 11, 4): 11_000_000.0,
        # Today's session turnover (should be ignored causally!)
        date(2026, 11, 5): 500_000_000.0,
    }

    mgr.register_instrument(
        instrument_id=4,
        isin="INE004D04044",
        listing_date=datetime(2020, 1, 1, tzinfo=IST),
        symbol_history=[("LIQUIDCORP", datetime(2020, 1, 1, tzinfo=IST), None)],
        historical_daily_turnover_inr=turnovers,
    )

    # Query at 10:00 AM on 2026-11-05
    as_of = datetime(2026, 11, 5, 10, 0, tzinfo=IST)

    # Prior median of [10M, 12M, 11M] = 11,000,000
    # If today's 500M was leaked, median would be 11.5M
    snap = mgr.get_point_in_time_universe(as_of=as_of, min_median_daily_turnover_inr=10_000_000.0)
    assert snap.eligible_count == 1
    member = snap.members[0]
    assert member.historical_median_daily_turnover_inr == 11_000_000.0

    # If filter requires 15M -> ineligible because prior median was 11M
    snap_strict = mgr.get_point_in_time_universe(
        as_of=as_of, min_median_daily_turnover_inr=15_000_000.0
    )
    assert snap_strict.eligible_count == 0
    assert snap_strict.members[0].is_eligible is False
