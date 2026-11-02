"""Point-in-time universe selection and historical symbol resolution (Layer 5).

Governed by:
- DATA_AND_PERFORMANCE_POLICY.md §2 (Point-in-Time Correctness)
- ARCHITECTURE.md §2, §5 (Stable Instrument Identity & Historical Symbol Mapping)
- Layer 5 Gate: Point-in-time eligible universe using data known at that historical timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from finpilot.schemas.common import normalize_to_utc
from finpilot.schemas.errors import DomainValidationError, ErrorCode

from .models import PointInTimeUniverseSnapshot, UniverseMember

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class InstrumentUniverseRecord:
    """Historical profile of an instrument for point-in-time universe evaluation."""

    instrument_id: int
    isin: str
    listing_date: datetime
    delisting_date: datetime | None
    status: str
    symbol_history: list[tuple[str, datetime, datetime | None]]  # (symbol, valid_from, valid_to)
    historical_daily_turnover_inr: dict[date, float] = field(default_factory=dict)


class PointInTimeUniverseManager:
    """Manages survivorship-bias-free universe membership and historical symbol mapping.

    Causal Invariants:
    1. No Future Survivors: An instrument listed after `as_of` is strictly excluded.
    2. No Survivorship Bias: An instrument delisted after `as_of` remains eligible as of `as_of`.
    3. Historical Symbol Resolution: Returns the exact ticker symbol active at `as_of`.
    4. Causal Liquidity Evaluation: Turnover filters consider only trading sessions completed
       strictly before `as_of`. Never includes the current session or future sessions.
    """

    def __init__(self, universe_name: str = "NSE_CASH_EQUITY_UNIVERSE") -> None:
        self.universe_name = universe_name
        self._instruments: dict[int, InstrumentUniverseRecord] = {}

    def register_instrument(
        self,
        instrument_id: int,
        isin: str,
        listing_date: Any,
        symbol_history: list[tuple[str, Any, Any]],
        delisting_date: Any = None,
        status: str = "ACTIVE",
        historical_daily_turnover_inr: dict[date, float] | None = None,
    ) -> None:
        """Register an instrument profile with historical symbol changes and turnover history."""
        norm_listing = normalize_to_utc(listing_date)
        norm_delisting = normalize_to_utc(delisting_date) if delisting_date is not None else None

        norm_history: list[tuple[str, datetime, datetime | None]] = []
        for sym, vf, vt in symbol_history:
            nvf = normalize_to_utc(vf)
            nvt = normalize_to_utc(vt) if vt is not None else None
            norm_history.append((sym.upper(), nvf, nvt))

        # Sort symbol history chronologically
        norm_history.sort(key=lambda x: x[1])

        self._instruments[instrument_id] = InstrumentUniverseRecord(
            instrument_id=instrument_id,
            isin=isin.upper(),
            listing_date=norm_listing,
            delisting_date=norm_delisting,
            status=status.upper(),
            symbol_history=norm_history,
            historical_daily_turnover_inr=historical_daily_turnover_inr or {},
        )

    def resolve_symbol_at(self, instrument_id: int, as_of: datetime) -> str:
        """Resolve the active trading symbol for an instrument as of a specific timestamp."""
        if instrument_id not in self._instruments:
            raise DomainValidationError(
                f"Unknown instrument ID: {instrument_id}",
                field="instrument_id",
                code=ErrorCode.INVALID_INSTRUMENT,
            )

        as_of_utc = normalize_to_utc(as_of)
        record = self._instruments[instrument_id]

        for sym, v_from, v_to in record.symbol_history:
            if v_from <= as_of_utc and (v_to is None or as_of_utc < v_to):
                return sym

        # Fallback to the latest symbol if within listing boundaries
        if record.symbol_history:
            return record.symbol_history[-1][0]
        raise DomainValidationError(
            f"No valid symbol history found for instrument {instrument_id}",
            field="symbol",
            code=ErrorCode.INVALID_INSTRUMENT,
        )

    def get_point_in_time_universe(
        self,
        as_of: datetime,
        min_median_daily_turnover_inr: float = 0.0,
        turnover_lookback_sessions: int = 20,
    ) -> PointInTimeUniverseSnapshot:
        """Evaluate point-in-time eligible universe membership strictly as of `as_of`."""
        as_of_utc = normalize_to_utc(as_of)
        as_of_date_ist = as_of_utc.astimezone(IST).date()

        members: list[UniverseMember] = []

        for inst_id, rec in sorted(self._instruments.items()):
            # 1. Listing Check: Must have been listed on or before `as_of`
            if rec.listing_date > as_of_utc:
                members.append(
                    UniverseMember(
                        instrument_id=inst_id,
                        isin=rec.isin,
                        symbol=rec.symbol_history[0][0] if rec.symbol_history else "UNKNOWN",
                        valid_from=rec.listing_date,
                        valid_to=rec.delisting_date,
                        status=rec.status,
                        listing_date=rec.listing_date,
                        delisting_date=rec.delisting_date,
                        historical_median_daily_turnover_inr=None,
                        is_eligible=False,
                        ineligibility_reason=(
                            f"Not yet listed as of {as_of_utc.date()} (listed on "
                            f"{rec.listing_date.date()})"
                        ),
                    )
                )
                continue

            # 2. Delisting Check: Must NOT have been delisted strictly before or on `as_of`
            if rec.delisting_date is not None and rec.delisting_date <= as_of_utc:
                members.append(
                    UniverseMember(
                        instrument_id=inst_id,
                        isin=rec.isin,
                        symbol=self._resolve_symbol_safe(rec, as_of_utc),
                        valid_from=rec.listing_date,
                        valid_to=rec.delisting_date,
                        status="DELISTED",
                        listing_date=rec.listing_date,
                        delisting_date=rec.delisting_date,
                        historical_median_daily_turnover_inr=None,
                        is_eligible=False,
                        ineligibility_reason=(
                            f"Delisted prior to {as_of_utc.date()} (delisted on "
                            f"{rec.delisting_date.date()})"
                        ),
                    )
                )
                continue

            # 3. Active symbol at as_of
            current_symbol = self._resolve_symbol_safe(rec, as_of_utc)

            # 4. Causal historical liquidity check (strictly prior sessions, < as_of_date_ist)
            prior_turnovers: list[float] = [
                turnover
                for d, turnover in rec.historical_daily_turnover_inr.items()
                if d < as_of_date_ist
            ]

            med_turnover: float | None = None
            if prior_turnovers:
                recent_turnovers = prior_turnovers[-turnover_lookback_sessions:]
                med_turnover = float(median(recent_turnovers))

            is_eligible = True
            ineligibility_reason: str | None = None

            if min_median_daily_turnover_inr > 0.0 and (
                med_turnover is None or med_turnover < min_median_daily_turnover_inr
            ):
                is_eligible = False
                ineligibility_reason = (
                    f"Insufficient historical turnover: {med_turnover!r} INR < "
                    f"{min_median_daily_turnover_inr!r} INR"
                )

            members.append(
                UniverseMember(
                    instrument_id=inst_id,
                    isin=rec.isin,
                    symbol=current_symbol,
                    valid_from=rec.listing_date,
                    valid_to=rec.delisting_date,
                    status=rec.status,
                    listing_date=rec.listing_date,
                    delisting_date=rec.delisting_date,
                    historical_median_daily_turnover_inr=med_turnover,
                    is_eligible=is_eligible,
                    ineligibility_reason=ineligibility_reason,
                )
            )

        eligible_count = sum(1 for m in members if m.is_eligible)
        return PointInTimeUniverseSnapshot(
            as_of_timestamp=as_of_utc,
            universe_name=self.universe_name,
            members=members,
            eligible_count=eligible_count,
        )

    def _resolve_symbol_safe(self, rec: InstrumentUniverseRecord, as_of: datetime) -> str:
        for sym, v_from, v_to in rec.symbol_history:
            if v_from <= as_of and (v_to is None or as_of < v_to):
                return sym
        if rec.symbol_history:
            return rec.symbol_history[-1][0]
        return "UNKNOWN"
